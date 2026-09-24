import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.conversation import ConversationSession
from app.ai.gemini_client import analyze_message
from app.services import registration_service

logger = logging.getLogger(__name__)

# Friendly labels for each required field when asking the caller
FIELD_QUESTIONS = {
    "first_name": "What is your first name?",
    "last_name": "What is your last name?",
    "date_of_birth": "What is your date of birth?",
    "sex": "What is your gender? I can accept male, female, other, or decline to answer.",
    "phone_number": "What is your 10-digit US phone number?",
    "address_line_1": "What is your street address?",
    "city": "What city do you live in?",
    "state": "What state? Please give me the two-letter abbreviation, like TX or CA.",
    "zip_code": "What is your ZIP code?",
}


def _next_question(missing: list[str]) -> str:
    for field in FIELD_QUESTIONS:
        if field in missing:
            return FIELD_QUESTIONS[field]
    return ""


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

    # Pass the last question asked as a hint so Gemini knows what field was being collected
    last_question = history[-1]["content"] if history and history[-1]["role"] == "assistant" else ""

    # --- Call Gemini for extraction only ---
    try:
        analysis = analyze_message(
            message=user_message,
            collected_data=patient_data,
            missing_fields=missing,
            registration_status=status,
            conversation_history=history,
            last_question=last_question,
        )
    except Exception as e:
        logger.error(f"Gemini failed: {e}")
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
    uncertain = set()
    asking_for_first = "first name" in last_question.lower()
    asking_for_last = "last name" in last_question.lower()

    if analysis.extracted_fields or analysis.corrected_fields:
        uncertain = set(analysis.uncertain_fields or [])
        safe_extracted = {k: v for k, v in analysis.extracted_fields.items() if k not in uncertain}

        extracted_keys = set(safe_extracted.keys())
        if (
            "first_name" in extracted_keys
            and "last_name" not in extracted_keys
            and not patient_data.get("first_name")
            and not patient_data.get("last_name")
            and not asking_for_first
            and not asking_for_last
        ):
            patient_data["_pending_name"] = safe_extracted.pop("first_name")
            uncertain.add("first_name")
        elif "name_ambiguous" in (analysis.extracted_fields or {}):
            patient_data["_pending_name"] = analysis.extracted_fields["name_ambiguous"]
            safe_extracted.pop("name_ambiguous", None)

        patient_data, validation_errors = registration_service.apply_extracted_fields(
            patient_data,
            safe_extracted,
            analysis.corrected_fields,
        )

    # --- Resolve pending ambiguous name ---
    pending_name = patient_data.get("_pending_name")
    if pending_name:
        msg_lower = user_message.lower()
        if asking_for_first or any(w in msg_lower for w in ["first", "given"]):
            patient_data["first_name"] = pending_name
            patient_data.pop("_pending_name", None)
        elif asking_for_last or any(w in msg_lower for w in ["last", "surname", "family"]):
            patient_data["last_name"] = pending_name
            patient_data.pop("_pending_name", None)

    # --- Recalculate missing after extraction ---
    missing = registration_service.get_missing_required_fields(
        {k: v for k, v in patient_data.items() if not k.startswith("_")}
    )

    # --- Echo back newly extracted fields for confirmation ---
    # For fields that are easy to mishear, repeat back what was captured
    ECHO_FIELDS = {
        "first_name": lambda v: f"Got it, first name {v}.",
        "last_name": lambda v: f"Last name {v}.",
        "date_of_birth": lambda v: f"Date of birth {v}.",
        "phone_number": lambda v: f"Phone number {v}.",
        "zip_code": lambda v: f"ZIP code {v}.",
    }
    newly_extracted = [
        k for k in (analysis.extracted_fields or {})
        if k in ECHO_FIELDS and k not in uncertain and k in patient_data and not validation_errors
    ]
    echo_prefix = " ".join(ECHO_FIELDS[k](patient_data[k]) for k in newly_extracted if k in patient_data)


    # --- Build response — backend owns all logic ---
    response_message = ""

    if status == "pending_confirmation":
        if analysis.confirmation_response == "yes":
            patient, error = registration_service.attempt_save_patient(db, patient_data)
            if error and error.startswith("DUPLICATE:"):
                existing_id = error.split(":")[1]
                status = "duplicate_found"
                response_message = (
                    "It looks like we already have a record with that phone number. "
                    "Would you like to update your existing record instead?"
                )
                patient_data["_duplicate_patient_id"] = existing_id
            elif error:
                logger.error(f"[SAVE ERROR] session={session_id} error={error}")
                response_message = f"I wasn't able to save your registration. {error} Could you correct that?"
                status = "in_progress"
            else:
                status = "completed"
                logger.info(f"[REGISTRATION COMPLETE] session={session_id} patient_id={patient.patient_id}")
                response_message = f"You're all set, {patient_data.get('first_name')}! Your registration is saved. Your patient ID is {patient.patient_id}. Goodbye!"
        elif analysis.confirmation_response == "no":
            status = "in_progress"
            response_message = "No problem. Which field would you like to change? For example, name, date of birth, phone number, or address?"
        else:
            # Re-read summary if they said something unclear
            summary = registration_service.format_patient_summary(
                {k: v for k, v in patient_data.items() if not k.startswith("_")}
            )
            response_message = f"Just to confirm: {summary}. Does everything look correct? Please say yes or no."

    elif status == "duplicate_found":
        if any(w in user_message.lower() for w in ["yes", "update", "yeah", "sure"]):
            dup_id = patient_data.pop("_duplicate_patient_id", None)
            if dup_id:
                from app.services.patient_service import update_patient
                from app.schemas.patient import PatientUpdate
                try:
                    update_data = PatientUpdate(**{k: v for k, v in patient_data.items() if not k.startswith("_")})
                    update_patient(db, dup_id, update_data)
                    status = "completed"
                    response_message = f"Your record has been updated. Patient ID: {dup_id}. Goodbye!"
                except Exception as e:
                    logger.error(f"[UPDATE ERROR] {e}")
                    response_message = "I had trouble updating your record. Please try again."
                    status = "in_progress"
        else:
            patient_data.pop("_duplicate_patient_id", None)
            status = "in_progress"
            response_message = "Understood. Let's start a new registration. " + _next_question(missing)

    elif status == "optional_offered":
        msg_lower = user_message.lower()
        declined = any(w in msg_lower for w in ["no", "nope", "skip", "that's all", "thats all", "no thanks", "none"])
        has_optional = any(k in analysis.extracted_fields for k in [
            "insurance_provider", "insurance_member_id", "emergency_contact_name",
            "emergency_contact_phone", "preferred_language", "email"
        ])
        pending_optional = patient_data.get("_pending_optional")  # "insurance" | "emergency"

        if declined and not pending_optional:
            # Declined the whole optional offer — go to confirmation
            patient_data.pop("_pending_optional", None)
            status = "pending_confirmation"
            summary = registration_service.format_patient_summary(
                {k: v for k, v in patient_data.items() if not k.startswith("_")}
            )
            response_message = f"Perfect. Here is what I have: {summary}. Does everything look correct? Please say yes to confirm or tell me what to change."

        elif pending_optional == "insurance":
            # We already asked for insurance — this turn should have the answer
            if has_optional or declined:
                # Got insurance data or they skipped — ask about emergency contact next
                patient_data.pop("_pending_optional", None)
                if not declined:
                    response_message = "Would you also like to provide an emergency contact or preferred language? Or say no to skip."
                else:
                    status = "pending_confirmation"
                    summary = registration_service.format_patient_summary(
                        {k: v for k, v in patient_data.items() if not k.startswith("_")}
                    )
                    response_message = f"Got it. Here is what I have: {summary}. Does everything look correct? Please say yes to confirm or tell me what to change."
            else:
                response_message = "Could you please provide your insurance provider name and member ID?"

        elif pending_optional == "emergency":
            # We already asked for emergency contact — this turn should have the answer
            patient_data.pop("_pending_optional", None)
            status = "pending_confirmation"
            summary = registration_service.format_patient_summary(
                {k: v for k, v in patient_data.items() if not k.startswith("_")}
            )
            response_message = f"Got it. Here is what I have: {summary}. Does everything look correct? Please say yes to confirm or tell me what to change."

        elif has_optional:
            # Caller volunteered optional data directly — ask if anything else
            response_message = "Would you also like to provide an emergency contact or preferred language? Or say no to skip."

        elif any(w in msg_lower for w in ["insur", "yes", "yeah", "sure", "ok", "okay", "i do", "i have"]):
            # Caller said yes to optional offer — ask for insurance first
            patient_data["_pending_optional"] = "insurance"
            response_message = "What is your insurance provider name and member ID?"

        elif any(w in msg_lower for w in ["emergency", "contact"]):
            patient_data["_pending_optional"] = "emergency"
            response_message = "What is the name and phone number for your emergency contact?"

        else:
            response_message = "Would you like to provide insurance information, an emergency contact, or preferred language? Or say no to skip."

    else:
        # status == "in_progress" (or None/new session)
        status = "in_progress"

        if validation_errors:
            response_message = validation_errors[0]
        elif patient_data.get("_pending_name"):
            response_message = f"Is '{patient_data['_pending_name']}' your first name or last name?"
        elif missing:
            response_message = _next_question(missing)
        else:
            # All required fields collected — check if we already offered optional fields
            if session.registration_status in ("optional_offered", "pending_confirmation"):
                # Coming back from a correction — re-read summary
                status = "pending_confirmation"
                summary = registration_service.format_patient_summary(
                    {k: v for k, v in patient_data.items() if not k.startswith("_")}
                )
                response_message = f"Got it. Here is the updated information: {summary}. Does everything look correct? Please say yes to confirm or tell me what else to change."
            else:
                # First time all required fields are complete — offer optional fields
                status = "optional_offered"
                response_message = (
                    "Great, I have all the required information. "
                    "Do you have any current insurance? Also, would you like to provide an emergency contact or preferred language?"
                )

    # Prepend echo of what was just captured (for key fields) so caller can catch mishearing
    if echo_prefix and status not in ("pending_confirmation", "completed") and not validation_errors:
        response_message = f"{echo_prefix} {response_message}"

    # --- Persist state ---
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": response_message})

    session.patient_data = patient_data
    session.conversation_history = history
    session.registration_status = status
    _save_session(db, session)

    public_fields = {k: v for k, v in patient_data.items() if not k.startswith("_")}

    return {
        "session_id": session_id,
        "message": response_message,
        "registration_status": status,
        "collected_fields": public_fields,
    }
