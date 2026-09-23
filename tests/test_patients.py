"""Integration-style tests for patient service and registration service logic."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date


# ── PatientService ────────────────────────────────────────────────────────────

class TestPatientService:

    def _make_patient(self, **kwargs):
        from datetime import datetime, timezone
        p = MagicMock()
        p.patient_id = kwargs.get("patient_id", "uuid-abc")
        p.first_name = kwargs.get("first_name", "Test")
        p.last_name = kwargs.get("last_name", "User")
        p.date_of_birth = kwargs.get("date_of_birth", date(1990, 1, 1))
        p.sex = kwargs.get("sex", "male")
        p.phone_number = kwargs.get("phone_number", "5550001111")
        p.address_line_1 = kwargs.get("address_line_1", "1 Test St")
        p.address_line_2 = None
        p.city = kwargs.get("city", "Testville")
        p.state = kwargs.get("state", "TX")
        p.zip_code = kwargs.get("zip_code", "75001")
        p.email = None
        p.insurance_provider = None
        p.insurance_member_id = None
        p.preferred_language = None
        p.emergency_contact_name = None
        p.emergency_contact_phone = None
        p.created_at = datetime.now(timezone.utc)
        p.updated_at = datetime.now(timezone.utc)
        p.deleted_at = None
        return p

    def test_find_by_phone_normalizes(self):
        from app.services.patient_service import find_by_phone
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        result = find_by_phone(db, "(555) 000-1111")
        # Should not raise; normalization happens internally
        assert result is None

    def test_soft_delete_sets_deleted_at(self):
        from app.services.patient_service import soft_delete_patient
        db = MagicMock()
        patient = self._make_patient()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = patient
        result = soft_delete_patient(db, "uuid-abc")
        assert result is True
        assert patient.deleted_at is not None

    def test_soft_delete_not_found(self):
        from app.services.patient_service import soft_delete_patient
        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        result = soft_delete_patient(db, "bad-id")
        assert result is False


# ── RegistrationService ───────────────────────────────────────────────────────

class TestRegistrationService:

    FULL_DATA = {
        "first_name": "Jane", "last_name": "Doe",
        "date_of_birth": "1985-06-20", "sex": "female",
        "phone_number": "5551234567", "address_line_1": "123 Main St",
        "city": "Austin", "state": "TX", "zip_code": "78701",
    }

    def test_get_missing_required_fields_all_present(self):
        from app.services.registration_service import get_missing_required_fields
        assert get_missing_required_fields(self.FULL_DATA) == []

    def test_get_missing_required_fields_partial(self):
        from app.services.registration_service import get_missing_required_fields
        partial = {"first_name": "Jane", "last_name": "Doe"}
        missing = get_missing_required_fields(partial)
        assert "date_of_birth" in missing
        assert "phone_number" in missing

    def test_apply_extracted_fields_valid(self):
        from app.services.registration_service import apply_extracted_fields
        data, errors = apply_extracted_fields({}, {"first_name": "Alice", "city": "Boston"}, {})
        assert data["first_name"] == "Alice"
        assert data["city"] == "Boston"
        assert errors == []

    def test_apply_extracted_fields_invalid_phone(self):
        from app.services.registration_service import apply_extracted_fields
        data, errors = apply_extracted_fields({}, {"phone_number": "999"}, {})
        assert "phone_number" not in data
        assert len(errors) == 1

    def test_apply_corrected_fields_overrides(self):
        from app.services.registration_service import apply_extracted_fields
        existing = {"last_name": "Smith"}
        data, errors = apply_extracted_fields(existing, {}, {"last_name": "Smyth"})
        assert data["last_name"] == "Smyth"
        assert errors == []

    def test_validate_patient_data_valid(self):
        from app.services.registration_service import validate_patient_data
        schema, errors = validate_patient_data(self.FULL_DATA)
        assert schema is not None
        assert errors == []

    def test_validate_patient_data_missing_required(self):
        from app.services.registration_service import validate_patient_data
        schema, errors = validate_patient_data({"first_name": "Jane"})
        assert schema is None
        assert len(errors) > 0

    def test_format_patient_summary(self):
        from app.services.registration_service import format_patient_summary
        summary = format_patient_summary(self.FULL_DATA)
        assert "Jane" in summary
        assert "Doe" in summary
        assert "Austin" in summary

    @patch("app.services.registration_service.patient_service.find_by_phone", return_value=None)
    @patch("app.services.registration_service.patient_service.create_patient")
    def test_attempt_save_patient_success(self, mock_create, mock_find):
        from app.services.registration_service import attempt_save_patient
        mock_patient = MagicMock()
        mock_patient.patient_id = "saved-uuid"
        mock_create.return_value = mock_patient
        db = MagicMock()
        patient, error = attempt_save_patient(db, self.FULL_DATA)
        assert patient is not None
        assert error is None

    @patch("app.services.registration_service.patient_service.find_by_phone")
    def test_attempt_save_patient_duplicate(self, mock_find):
        from app.services.registration_service import attempt_save_patient
        existing = MagicMock()
        existing.patient_id = "dup-uuid"
        mock_find.return_value = existing
        db = MagicMock()
        patient, error = attempt_save_patient(db, self.FULL_DATA)
        assert patient is None
        assert "DUPLICATE:dup-uuid" == error

    def test_attempt_save_invalid_data(self):
        from app.services.registration_service import attempt_save_patient
        db = MagicMock()
        patient, error = attempt_save_patient(db, {"first_name": "Only"})
        assert patient is None
        assert error is not None


# ── Validation Utils ──────────────────────────────────────────────────────────

class TestValidationUtils:

    def test_normalize_phone_with_formatting(self):
        from app.utils.validation import normalize_phone
        assert normalize_phone("(555) 123-4567") == "5551234567"
        assert normalize_phone("555-123-4567") == "5551234567"
        assert normalize_phone("15551234567") == "5551234567"

    def test_normalize_phone_invalid(self):
        from app.utils.validation import normalize_phone
        assert normalize_phone("123") is None
        assert normalize_phone("abcdefghij") is None

    def test_normalize_zip_valid(self):
        from app.utils.validation import normalize_zip
        assert normalize_zip("75201") == "75201"
        assert normalize_zip("75201-1234") == "75201-1234"

    def test_normalize_zip_invalid(self):
        from app.utils.validation import normalize_zip
        assert normalize_zip("ABCDE") is None
        assert normalize_zip("1234") is None

    def test_validate_dob_future(self):
        from app.utils.validation import validate_dob
        from datetime import date, timedelta
        future = date.today() + timedelta(days=1)
        assert validate_dob(future) is not None

    def test_validate_dob_valid(self):
        from app.utils.validation import validate_dob
        assert validate_dob(date(1990, 5, 15)) is None

    def test_validate_sex_variants(self):
        from app.utils.validation import validate_sex
        assert validate_sex("M") == "male"
        assert validate_sex("Female") == "female"
        assert validate_sex("OTHER") == "other"
        assert validate_sex("xyz") is None

    def test_validate_email(self):
        from app.utils.validation import validate_email
        assert validate_email("user@example.com") is True
        assert validate_email("not-an-email") is False
        assert validate_email("missing@domain") is False
