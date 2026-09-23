import re
from datetime import date


def normalize_phone(phone: str) -> str | None:
    """Strip non-digits and accept 7-15 digit phone numbers (international friendly)."""
    digits = re.sub(r"\D", "", phone)
    if 7 <= len(digits) <= 15:
        return digits
    return None


def normalize_zip(zip_code: str) -> str | None:
    """Accept US ZIP or any 4-10 digit postal code."""
    cleaned = zip_code.strip()
    if re.match(r"^\d{4,10}(-\d{4})?$", cleaned):
        return cleaned
    return None


def validate_dob(dob: date) -> str | None:
    """Return error string if DOB is invalid, else None."""
    today = date.today()
    if dob > today:
        return "Date of birth cannot be in the future."
    if dob.year < 1900:
        return "Date of birth seems too far in the past."
    return None


def validate_sex(sex: str) -> str | None:
    """Normalize and validate sex field."""
    normalized = sex.strip().lower()
    mapping = {
        "male": "male", "m": "male",
        "female": "female", "f": "female",
        "other": "other", "o": "other",
        "prefer not to say": "prefer not to say",
    }
    return mapping.get(normalized)


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))
