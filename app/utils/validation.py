import re
from datetime import date

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}


def normalize_phone(phone: str) -> str | None:
    """Strip non-digits, validate US 10-digit phone number."""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def normalize_zip(zip_code: str) -> str | None:
    """Validate US ZIP code (5 digits or ZIP+4)."""
    cleaned = zip_code.strip()
    if re.match(r"^\d{5}(-\d{4})?$", cleaned):
        return cleaned
    return None


def validate_state(state: str) -> str | None:
    """Validate and normalize 2-letter US state abbreviation."""
    normalized = state.strip().upper()
    return normalized if normalized in US_STATES else None


def validate_name(name: str) -> str | None:
    """Validate name: 1-50 chars, alphabetic + hyphens/apostrophes."""
    cleaned = name.strip()
    if 1 <= len(cleaned) <= 50 and re.match(r"^[A-Za-z\-']+$", cleaned):
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
        "decline to answer": "decline to answer",
        "decline": "decline to answer",
        "prefer not to say": "decline to answer",
    }
    return mapping.get(normalized)


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))
