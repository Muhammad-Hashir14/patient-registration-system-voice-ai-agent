import logging
from datetime import date
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.schemas.patient import PatientCreate, REQUIRED_FIELDS, OPTIONAL_FIELDS, ALL_FIELDS
from app.services import patient_service

logger = logging.getLogger(__name__)


def get_missing_required_fields(patient_data: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not patient_data.get(f)]


def format_patient_summary(patient_data: dict) -> str:
    parts = [
        f"{patient_data.get('first_name', '')} {patient_data.get('last_name', '')}",
        f"date of birth {patient_data.get('date_of_birth', '')}",
        f"gender {patient_data.get('sex', '')}",
        f"phone {patient_data.get('phone_number', '')}",
        f"address {patient_data.get('address_line_1', '')}"
        + (f" {patient_data.get('address_line_2')}" if patient_data.get('address_line_2') else ""),
        f"{patient_data.get('city', '')}, {patient_data.get('state', '')} {patient_data.get('zip_code', '')}",
    ]
    if patient_data.get("email"):
        parts.append(f"email {patient_data['email']}")
    if patient_data.get("insurance_provider"):
        parts.append(f"insurance {patient_data['insurance_provider']}"
                     + (f" member ID {patient_data['insurance_member_id']}" if patient_data.get('insurance_member_id') else ""))
    if patient_data.get("emergency_contact_name"):
        parts.append(f"emergency contact {patient_data['emergency_contact_name']}"
                     + (f" at {patient_data['emergency_contact_phone']}" if patient_data.get('emergency_contact_phone') else ""))
    return ", ".join(parts)


def validate_patient_data(patient_data: dict) -> tuple[PatientCreate | None, list[str]]:
    """Try to build a PatientCreate. Returns (schema, errors)."""
    try:
        schema = PatientCreate(**patient_data)
        return schema, []
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        return None, errors


def apply_extracted_fields(
    patient_data: dict,
    extracted: dict,
    corrected: dict,
) -> tuple[dict, list[str]]:
    """
    Merge extracted and corrected fields into patient_data.
    Returns (updated_data, validation_errors).
    """
    updated = dict(patient_data)
    validation_errors = []

    # Apply corrections first, then new extractions
    merged = {**extracted, **corrected}

    for field, value in merged.items():
        if field not in ALL_FIELDS or value is None or value == "":
            continue

        # Field-level pre-validation before storing
        error = _validate_single_field(field, value)
        if error:
            validation_errors.append(error)
        else:
            # Normalize before storing
            updated[field] = _normalize_field(field, value)

    return updated, validation_errors


def _validate_single_field(field: str, value) -> str | None:
    from app.utils.validation import normalize_phone, normalize_zip, validate_sex, validate_email, validate_state, validate_name
    if field in ("first_name", "last_name"):
        if not validate_name(str(value)):
            return f"'{value}' doesn't look like a valid name. Please use letters, hyphens, or apostrophes only (1-50 characters)."
    elif field == "phone_number":
        if not normalize_phone(str(value)):
            return f"'{value}' doesn't look like a valid US phone number. Please provide a 10-digit number."
    elif field == "state":
        if not validate_state(str(value)):
            return f"'{value}' isn't a valid US state. Please provide a 2-letter abbreviation like TX or CA."
    elif field == "zip_code":
        if not normalize_zip(str(value)):
            return f"'{value}' doesn't look like a valid US ZIP code."
    elif field == "sex":
        if not validate_sex(str(value)):
            return f"For sex, I can accept male, female, other, or decline to answer."
    elif field == "email":
        if not validate_email(str(value)):
            return f"'{value}' doesn't look like a valid email address."
    elif field == "date_of_birth":
        try:
            dob = _parse_date(value)
            from app.utils.validation import validate_dob
            err = validate_dob(dob)
            if err:
                return err
        except Exception:
            return f"I couldn't parse '{value}' as a date. Could you provide it as MM/DD/YYYY?"
    return None


def _normalize_field(field: str, value):
    from app.utils.validation import normalize_phone, normalize_zip, validate_sex, validate_state
    if field == "phone_number":
        return normalize_phone(str(value))
    if field == "zip_code":
        return normalize_zip(str(value))
    if field == "sex":
        return validate_sex(str(value))
    if field == "state":
        return validate_state(str(value))
    if field == "date_of_birth":
        return str(_parse_date(value))
    return value


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    from dateutil import parser as dateparser
    return dateparser.parse(str(value)).date()


def attempt_save_patient(db: Session, patient_data: dict) -> tuple[object | None, str | None]:
    """
    Validate fully, check duplicates, and save.
    Returns (patient, error_message).
    """
    schema, errors = validate_patient_data(patient_data)
    if errors:
        logger.error(f"[SAVE FAILED] validation errors: {errors} | data: {patient_data}")
        return None, "There are some issues: " + "; ".join(errors)

    existing = patient_service.find_by_phone(db, schema.phone_number)
    if existing:
        return None, f"DUPLICATE:{existing.patient_id}"

    patient = patient_service.create_patient(db, schema)
    return patient, None
