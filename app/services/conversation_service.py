import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.conversation import ConversationSession
from app.ai.gemini_client import analyze_message
from app.services import registration_service

logger = logging.getLogger(__name__)


def _get_or_create_session(db: Session, session_id: str) -> ConversationSession:
    session = db.query(ConversationSession).filter(
        ConversationSession.session_id == session_id
    ).first()
    if not session:
        session = ConversationSession(session_id=session_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _save_session(db: Session, session: ConversationSession):
    session.updated_at = datetime.now(timezone.utc)
    db.commit()


def process_message(db: Session, session_id: str, user_message: str) -> dict:
    session = _get_or_create_session(db, session_id)

    patient_data: dict = dict(session.patient_data or {})
    history: list = list(session.conversation_history or [])
    status: str = session.registration_status

    missing = registration_service.get_missing_required_fields(
        {k: v for k, v in patient_data.items() if not k.startswith("_")}
    )

    # --- Call Gemini ---
    try:
        analysis = analyze_message(
            message=user_message,
            collected_data=patient_data,
            missing_fields=missing,
            registration_status=status,
            conversation_history=history,
        )
    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        # Preserve state, return graceful fallback
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": "I'm sorry, I had a technical issue. Could you repeat that?"})
        session.conversation_history = history
        _save_session(db, session)
        return {
            "session_id": session_id,
            "message": "I'm sorry, I had a technical issue. Could you repeat that?",
            "registration_status": status,
            "collected_fields": patient_data,
        }

    # --- Apply extracted/corrected fields ---
    validation_errors = []
    if analysis.extracted_fields or analysis.corrected_fields:
        # Don't store fields Gemini flagged as spelling-uncertain yet
        uncertain = set(analysis.uncertain_fields or [])
        safe_extracted = {k: v for k, v in analysis.extracted_fields.items() if k not in uncertain}

        # Handle single ambiguous name — store temporarily until caller clarifies
        if "name_ambiguous" in uncertain and "name_ambiguous" in analysis.extracted_fields:
            patient_data["_pending_name"] = analysis.extracted_fields["name_ambiguous"]

        patient_data, validation_errors = registration_service.apply_extracted_fields(
            patient_data,
            safe_extracted,
            analysis.corrected_fields,
        )

    # --- Resolve pending ambiguous name if caller just clarified ---
    pending_name = patient_data.get("_pending_name")
    if pending_name:
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["first", "first name", "given"]):
            patient_data["first_name"] = pending_name
            patient_data.pop("_pending_name", None)
        elif any(w in msg_lower for w in ["last", "last name", "surname", "family"]):
            patient_data["last_name"] = pending_name
            patient_data.pop("_pending_name", None)

    # --- Determine response ---
    response_message = analysis.suggested_response

    # Append validation error feedback if any
    if validation_errors:
        error_text = " ".join(validation_errors)
        response_message = f"{response_message} However, I noticed: {error_text}"

    # --- Handle confirmation flow ---
    if status == "pending_confirmation":
        if analysis.confirmation_response == "yes":
            patient, error = registration_service.attempt_save_patient(db, patient_data)
            if error and error.startswith("DUPLICATE:"):
                existing_id = error.split(":")[1]
                status = "duplicate_found"
                response_message = (
                    "It looks like there's already a patient registered with that phone number. "
                    "Would you like to update your existing record instead?"
                )
                patient_data["_duplicate_patient_id"] = existing_id
            elif error:
                response_message = f"I wasn't able to save your registration. {error} Could you correct that?"
                status = "in_progress"
            else:
                status = "completed"
                logger.info(f"[REGISTRATION COMPLETE] session={session_id} data={patient_data}")
                response_message = (
                    f"You're all set! Your registration has been saved successfully. "
                    f"Your patient ID is {patient.patient_id}. Is there anything else I can help you with?"
                )
        elif analysis.confirmation_response == "no":
            status = "in_progress"
            response_message = "No problem! What would you like to change?"

    elif status == "duplicate_found":
        # User responded to duplicate prompt
        if analysis.confirmation_response == "yes" or any(
            word in user_message.lower() for word in ["yes", "update", "yeah", "sure", "correct"]
        ):
            dup_id = patient_data.pop("_duplicate_patient_id", None)
            if dup_id:
                from app.services.patient_service import update_patient
                from app.schemas.patient import PatientUpdate
                try:
                    update_data = PatientUpdate(**{k: v for k, v in patient_data.items() if not k.startswith("_")})
                    update_patient(db, dup_id, update_data)
                    status = "completed"
                    response_message = f"Your existing record has been updated. Patient ID: {dup_id}."
                except Exception as e:
                    response_message = f"I had trouble updating your record. Please try again."
                    status = "in_progress"
        else:
            patient_data.pop("_duplicate_patient_id", None)
            status = "in_progress"
            response_message = "Understood. Let's continue with a new registration. What would you like to change?"

    elif status == "in_progress":
        missing = registration_service.get_missing_required_fields(
            {k: v for k, v in patient_data.items() if not k.startswith("_")}
        )
        if not missing and not validation_errors and not patient_data.get("_pending_name"):
            # All required fields collected — offer optional fields first
            status = "optional_offered"
            response_message = (
                "Great, I have all the required information. "
                "I can also collect your insurance information, emergency contact, and preferred language. "
                "Would you like to provide any of those?"
            )

    elif status == "optional_offered":
        # Move to confirmation only when caller declines optional fields or after they've provided them
        msg_lower = user_message.lower()
        declined = any(w in msg_lower for w in ["no", "nope", "skip", "that's all", "thats all", "no thanks", "none"])
        # If caller is still providing optional info, stay in optional_offered
        has_optional = any(k in analysis.extracted_fields for k in [
            "insurance_provider", "insurance_member_id", "emergency_contact_name",
            "emergency_contact_phone", "preferred_language", "email"
        ])
        accepted = any(w in msg_lower for w in ["yes", "yeah", "sure", "ok", "okay", "please"])
        if declined or (has_optional and not accepted):
            # Caller provided optional fields or declined — move to confirmation
            status = "pending_confirmation"
            summary = registration_service.format_patient_summary(
                {k: v for k, v in patient_data.items() if not k.startswith("_")}
            )
            response_message = (
                f"Perfect. Let me read everything back to you: "
                f"{summary} "
                f"Does everything look correct? Please say yes to confirm or let me know what to change."
            )
        # else: caller said yes or is still providing info — let Gemini's suggested_response guide them

    # --- Persist state ---
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_message})

    session.patient_data = patient_data
    session.conversation_history = history
    session.registration_status = status
    _save_session(db, session)

    # Return only non-internal fields
    public_fields = {k: v for k, v in patient_data.items() if not k.startswith("_")}

    return {
        "session_id": session_id,
        "message": response_message,
        "registration_status": status,
        "collected_fields": public_fields,
    }
