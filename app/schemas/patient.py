from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, field_validator


REQUIRED_FIELDS = [
    "first_name", "last_name", "date_of_birth", "sex",
    "phone_number", "address_line_1", "city", "state", "zip_code"
]

OPTIONAL_FIELDS = [
    "email", "address_line_2", "insurance_provider", "insurance_member_id",
    "preferred_language", "emergency_contact_name", "emergency_contact_phone"
]

ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS


class PatientCreate(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str
    email: str | None = None
    address_line_2: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_dob(cls, v) -> date:
        if isinstance(v, date):
            return v
        try:
            from dateutil import parser as dp
            return dp.parse(str(v)).date()
        except Exception:
            raise ValueError(f"Cannot parse '{v}' as a date. Use MM/DD/YYYY format.")

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        if v.year < 1900:
            raise ValueError("Date of birth seems too far in the past.")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        from app.utils.validation import validate_name
        result = validate_name(v)
        if not result:
            raise ValueError("Name must be 1-50 characters, letters, hyphens, or apostrophes only.")
        return result

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        from app.utils.validation import normalize_phone
        result = normalize_phone(v)
        if not result:
            raise ValueError("Invalid US phone number. Please provide a 10-digit US phone number.")
        return result

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        from app.utils.validation import validate_state
        result = validate_state(v)
        if not result:
            raise ValueError("State must be a valid 2-letter US state abbreviation (e.g. TX, CA).")
        return result

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        from app.utils.validation import normalize_zip
        result = normalize_zip(v)
        if not result:
            raise ValueError("Invalid US ZIP code.")
        return result

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: str) -> str:
        from app.utils.validation import validate_sex
        result = validate_sex(v)
        if not result:
            raise ValueError("Sex must be male, female, other, or decline to answer.")
        return result

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.utils.validation import validate_email
        if not validate_email(v):
            raise ValueError("Invalid email address.")
        return v.strip()


class PatientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    phone_number: str | None = None
    address_line_1: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    email: str | None = None
    address_line_2: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_dob(cls, v) -> date | None:
        if v is None or isinstance(v, date):
            return v
        try:
            from dateutil import parser as dp
            return dp.parse(str(v)).date()
        except Exception:
            raise ValueError(f"Cannot parse '{v}' as a date.")

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.utils.validation import validate_name
        result = validate_name(v)
        if not result:
            raise ValueError("Name must be 1-50 characters, letters, hyphens, or apostrophes only.")
        return result

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.utils.validation import validate_state
        result = validate_state(v)
        if not result:
            raise ValueError("State must be a valid 2-letter US state abbreviation (e.g. TX, CA).")
        return result

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.utils.validation import validate_sex
        result = validate_sex(v)
        if not result:
            raise ValueError("Sex must be male, female, other, or decline to answer.")
        return result


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    zip_code: str
    email: str | None
    insurance_provider: str | None
    insurance_member_id: str | None
    preferred_language: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    created_at: datetime
    updated_at: datetime
