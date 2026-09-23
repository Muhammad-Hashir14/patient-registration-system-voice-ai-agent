"""
Tests for the /chat endpoint covering all required conversational scenarios.
Uses pytest with FastAPI TestClient and mocks Gemini + DB.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.ai.schemas import ConversationAnalysis

client = TestClient(app)

SESSION_ID = "test-session-001"


def make_analysis(**kwargs) -> ConversationAnalysis:
    defaults = dict(
        intents=["provide_info"],
        extracted_fields={},
        corrected_fields={},
        user_question=None,
        needs_clarification=False,
        clarification_reason=None,
        registration_relevant=True,
        confirmation_response=None,
        suggested_response="Got it!",
    )
    defaults.update(kwargs)
    return ConversationAnalysis(**defaults)


def mock_session(patient_data=None, history=None, status="in_progress"):
    session = MagicMock()
    session.session_id = SESSION_ID
    session.patient_data = patient_data or {}
    session.conversation_history = history or []
    session.registration_status = status
    return session


def post_chat(message: str, session_id: str = SESSION_ID):
    return client.post("/chat", json={"session_id": session_id, "message": message})


# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db_session():
    """Patch get_db to return a mock DB session that returns a fresh ConversationSession."""
    with patch("app.api.routes_chat.get_db") as mock_get_db:
        db = MagicMock()
        mock_get_db.return_value = iter([db])

        # Default: no existing session → create new
        db.query.return_value.filter.return_value.first.return_value = None
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock(side_effect=lambda obj: setattr(obj, "session_id", SESSION_ID)
                               if not hasattr(obj, "session_id") else None)
        yield db


# ── Greeting & Small Talk ─────────────────────────────────────────────────────

class TestGreetingsAndSmallTalk:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_hello(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["greeting"],
            suggested_response="Hello! I'm your patient registration assistant. What's your name?"
        )
        r = post_chat("Hello")
        assert r.status_code == 200
        assert r.json()["error"] is None
        assert "Hello" in r.json()["data"]["message"] or "hello" in r.json()["data"]["message"].lower()

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_hi_how_are_you(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["greeting", "small_talk"],
            suggested_response="I'm doing great, thanks for asking! Ready to help with your registration."
        )
        r = post_chat("Hi, how are you?")
        assert r.status_code == 200
        assert r.json()["error"] is None

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_are_you_available(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["small_talk"],
            suggested_response="Yes, I'm here and ready to help. Whenever you're ready, we can start your registration."
        )
        r = post_chat("Are you available?")
        assert r.status_code == 200
        assert "ready" in r.json()["data"]["message"].lower() or "here" in r.json()["data"]["message"].lower()

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_are_you_human(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["question"],
            user_question="Are you a human?",
            suggested_response="No, I'm an AI assistant here to help with your registration."
        )
        r = post_chat("Are you a human?")
        assert r.status_code == 200
        assert "AI" in r.json()["data"]["message"] or "ai" in r.json()["data"]["message"].lower()

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_unrelated_weather(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["unrelated"],
            registration_relevant=False,
            suggested_response="I'm focused on patient registration, but I'd be happy to help with that. What's your name?"
        )
        r = post_chat("What's the weather?")
        assert r.status_code == 200
        assert r.json()["error"] is None


# ── Single Field Extraction ───────────────────────────────────────────────────

class TestSingleFieldExtraction:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_first_name_only(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"first_name": "John"},
            suggested_response="Nice to meet you, John! What's your last name?"
        )
        r = post_chat("I'm John.")
        assert r.status_code == 200
        assert r.json()["data"]["collected_fields"].get("first_name") == "John"

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_dob_natural_language(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"date_of_birth": "1990-03-15"},
            suggested_response="Got it, March 15, 1990. What's your sex?"
        )
        r = post_chat("My birthday is March 15, 1990.")
        assert r.status_code == 200
        assert r.json()["data"]["collected_fields"].get("date_of_birth") == "1990-03-15"

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_age_not_converted_to_dob(self, mock_save, mock_get_session, mock_analyze):
        """'I'm 35' must NOT produce a date_of_birth."""
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={},  # Gemini correctly returns nothing
            suggested_response="I see you're 35, but I'll need your exact date of birth. What is it?"
        )
        r = post_chat("I'm 35.")
        assert r.status_code == 200
        assert "date_of_birth" not in r.json()["data"]["collected_fields"]


# ── Multi-Field Extraction ────────────────────────────────────────────────────

class TestMultiFieldExtraction:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_name_and_city(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"first_name": "John", "last_name": "Smith", "city": "Dallas"},
            suggested_response="Nice to meet you, John Smith! I see you're in Dallas. What's your date of birth?"
        )
        r = post_chat("Hi, I'm John Smith and I live in Dallas.")
        assert r.status_code == 200
        fields = r.json()["data"]["collected_fields"]
        assert fields.get("first_name") == "John"
        assert fields.get("last_name") == "Smith"
        assert fields.get("city") == "Dallas"


# ── Corrections ───────────────────────────────────────────────────────────────

class TestCorrections:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_last_name_correction(self, mock_save, mock_get_session, mock_analyze):
        existing = mock_session(patient_data={"first_name": "John", "last_name": "Smith"})
        mock_get_session.return_value = existing
        mock_analyze.return_value = make_analysis(
            intents=["correction"],
            corrected_fields={"last_name": "Smyth"},
            suggested_response="Got it, I've updated your last name to Smyth."
        )
        r = post_chat("Actually, my last name is Smyth.")
        assert r.status_code == 200
        assert r.json()["data"]["collected_fields"].get("last_name") == "Smyth"

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_pause_message(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["pause"],
            suggested_response="Of course, take your time. I'll be here when you're ready."
        )
        r = post_chat("Wait.")
        assert r.status_code == 200
        assert r.json()["error"] is None


# ── Registration Questions ────────────────────────────────────────────────────

class TestRegistrationQuestions:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_why_dob_question(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["question"],
            user_question="Why do you need my date of birth?",
            suggested_response=(
                "We use your date of birth to verify your identity and ensure accurate medical records. "
                "Could you share it with me?"
            )
        )
        r = post_chat("Why do you need my date of birth?")
        assert r.status_code == 200
        assert r.json()["error"] is None

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_decline_optional_email(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            intents=["provide_info"],
            extracted_fields={},
            suggested_response="No problem at all! Email is optional. Let's continue."
        )
        r = post_chat("I don't want to give my email.")
        assert r.status_code == 200
        assert r.json()["error"] is None


# ── Validation ────────────────────────────────────────────────────────────────

class TestValidation:

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_invalid_dob_future(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"date_of_birth": "2099-01-01"},
            suggested_response="I'll try to save that date of birth."
        )
        r = post_chat("My DOB is January 1, 2099.")
        assert r.status_code == 200
        # Validation error should be appended to message
        assert "future" in r.json()["data"]["message"].lower() or "date_of_birth" not in r.json()["data"]["collected_fields"]

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_invalid_phone(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"phone_number": "123"},
            suggested_response="Got your phone number."
        )
        r = post_chat("My phone is 123.")
        assert r.status_code == 200
        # Invalid phone should not be stored
        assert "phone_number" not in r.json()["data"]["collected_fields"]

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_invalid_zip(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"zip_code": "ABCDE"},
            suggested_response="Got your ZIP."
        )
        r = post_chat("My ZIP is ABCDE.")
        assert r.status_code == 200
        assert "zip_code" not in r.json()["data"]["collected_fields"]

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_valid_phone_normalized(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session()
        mock_analyze.return_value = make_analysis(
            extracted_fields={"phone_number": "(555) 867-5309"},
            suggested_response="Got your phone number."
        )
        r = post_chat("My phone is (555) 867-5309.")
        assert r.status_code == 200
        assert r.json()["data"]["collected_fields"].get("phone_number") == "5558675309"


# ── Confirmation Flow ─────────────────────────────────────────────────────────

class TestConfirmationFlow:

    FULL_DATA = {
        "first_name": "Jane", "last_name": "Doe",
        "date_of_birth": "1985-06-20", "sex": "female",
        "phone_number": "5551234567", "address_line_1": "123 Main St",
        "city": "Austin", "state": "TX", "zip_code": "78701",
    }

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_all_fields_triggers_confirmation(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session(patient_data=self.FULL_DATA)
        mock_analyze.return_value = make_analysis(
            extracted_fields={},
            suggested_response="Let me confirm your details."
        )
        r = post_chat("That's all my info.")
        assert r.status_code == 200
        assert r.json()["data"]["registration_status"] == "pending_confirmation"

    @patch("app.services.registration_service.attempt_save_patient")
    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_confirmation_yes_saves(self, mock_save, mock_get_session, mock_analyze, mock_attempt_save):
        session = mock_session(patient_data=self.FULL_DATA, status="pending_confirmation")
        mock_get_session.return_value = session
        mock_analyze.return_value = make_analysis(
            intents=["confirmation"],
            confirmation_response="yes",
            suggested_response="Confirming your registration."
        )
        saved_patient = MagicMock()
        saved_patient.patient_id = "uuid-1234"
        mock_attempt_save.return_value = (saved_patient, None)

        r = post_chat("Yes, everything is correct.")
        assert r.status_code == 200
        assert r.json()["data"]["registration_status"] == "completed"
        assert "uuid-1234" in r.json()["data"]["message"]

    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_confirmation_no_returns_to_in_progress(self, mock_save, mock_get_session, mock_analyze):
        session = mock_session(patient_data=self.FULL_DATA, status="pending_confirmation")
        mock_get_session.return_value = session
        mock_analyze.return_value = make_analysis(
            intents=["confirmation"],
            confirmation_response="no",
            suggested_response="No problem, what would you like to change?"
        )
        r = post_chat("No, my phone number is wrong.")
        assert r.status_code == 200
        assert r.json()["data"]["registration_status"] == "in_progress"


# ── Duplicate Detection ───────────────────────────────────────────────────────

class TestDuplicateDetection:

    FULL_DATA = {
        "first_name": "Jane", "last_name": "Doe",
        "date_of_birth": "1985-06-20", "sex": "female",
        "phone_number": "5551234567", "address_line_1": "123 Main St",
        "city": "Austin", "state": "TX", "zip_code": "78701",
    }

    @patch("app.services.registration_service.attempt_save_patient")
    @patch("app.services.conversation_service.analyze_message")
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_duplicate_phone_detected(self, mock_save, mock_get_session, mock_analyze, mock_attempt_save):
        session = mock_session(patient_data=self.FULL_DATA, status="pending_confirmation")
        mock_get_session.return_value = session
        mock_analyze.return_value = make_analysis(
            confirmation_response="yes",
            suggested_response="Confirming."
        )
        mock_attempt_save.return_value = (None, "DUPLICATE:existing-uuid-999")

        r = post_chat("Yes, that's correct.")
        assert r.status_code == 200
        assert r.json()["data"]["registration_status"] == "duplicate_found"
        assert "already" in r.json()["data"]["message"].lower() or "existing" in r.json()["data"]["message"].lower()


# ── Gemini Failure ────────────────────────────────────────────────────────────

class TestGeminiFailure:

    @patch("app.services.conversation_service.analyze_message", side_effect=Exception("Gemini timeout"))
    @patch("app.services.conversation_service._get_or_create_session")
    @patch("app.services.conversation_service._save_session")
    def test_gemini_failure_graceful(self, mock_save, mock_get_session, mock_analyze):
        mock_get_session.return_value = mock_session(patient_data={"first_name": "John"})
        r = post_chat("Hello")
        assert r.status_code == 200
        assert "technical" in r.json()["data"]["message"].lower()
        # Existing state preserved
        assert r.json()["data"]["collected_fields"].get("first_name") == "John"


# ── Patient CRUD ──────────────────────────────────────────────────────────────

class TestPatientCRUD:

    VALID_PATIENT = {
        "first_name": "Alice", "last_name": "Walker",
        "date_of_birth": "1990-05-10", "sex": "female",
        "phone_number": "5559876543", "address_line_1": "456 Oak Ave",
        "city": "Houston", "state": "TX", "zip_code": "77001",
    }

    @patch("app.api.routes_patients.patient_service.find_by_phone", return_value=None)
    @patch("app.api.routes_patients.patient_service.create_patient")
    @patch("app.api.routes_patients.get_db")
    def test_create_patient(self, mock_get_db, mock_create, mock_find):
        db = MagicMock()
        mock_get_db.return_value = iter([db])
        from datetime import datetime, timezone, date
        patient = MagicMock()
        patient.patient_id = "new-uuid"
        patient.first_name = "Alice"
        patient.last_name = "Walker"
        patient.date_of_birth = date(1990, 5, 10)
        patient.sex = "female"
        patient.phone_number = "5559876543"
        patient.address_line_1 = "456 Oak Ave"
        patient.address_line_2 = None
        patient.city = "Houston"
        patient.state = "TX"
        patient.zip_code = "77001"
        patient.email = None
        patient.insurance_provider = None
        patient.insurance_member_id = None
        patient.preferred_language = None
        patient.emergency_contact_name = None
        patient.emergency_contact_phone = None
        patient.created_at = datetime.now(timezone.utc)
        patient.updated_at = datetime.now(timezone.utc)
        mock_create.return_value = patient

        r = client.post("/patients", json=self.VALID_PATIENT)
        assert r.status_code == 201
        assert r.json()["data"]["patient_id"] == "new-uuid"

    @patch("app.api.routes_patients.patient_service.get_patient", return_value=None)
    @patch("app.api.routes_patients.get_db")
    def test_get_patient_not_found(self, mock_get_db, mock_get):
        db = MagicMock()
        mock_get_db.return_value = iter([db])
        r = client.get("/patients/nonexistent-id")
        assert r.status_code == 404

    @patch("app.api.routes_patients.patient_service.soft_delete_patient", return_value=True)
    @patch("app.api.routes_patients.get_db")
    def test_soft_delete(self, mock_get_db, mock_delete):
        db = MagicMock()
        mock_get_db.return_value = iter([db])
        r = client.delete("/patients/some-uuid")
        assert r.status_code == 200
        assert "deleted" in r.json()["data"]["message"].lower()

    @patch("app.api.routes_patients.patient_service.soft_delete_patient", return_value=False)
    @patch("app.api.routes_patients.get_db")
    def test_soft_delete_not_found(self, mock_get_db, mock_delete):
        db = MagicMock()
        mock_get_db.return_value = iter([db])
        r = client.delete("/patients/bad-uuid")
        assert r.status_code == 404

    def test_create_patient_invalid_phone(self):
        bad = {**self.VALID_PATIENT, "phone_number": "123"}
        r = client.post("/patients", json=bad)
        assert r.status_code == 422

    def test_create_patient_future_dob(self):
        bad = {**self.VALID_PATIENT, "date_of_birth": "2099-01-01"}
        r = client.post("/patients", json=bad)
        assert r.status_code == 422

    def test_create_patient_invalid_zip(self):
        bad = {**self.VALID_PATIENT, "zip_code": "ABCDE"}
        r = client.post("/patients", json=bad)
        assert r.status_code == 422


# ── Pydantic Validation Unit Tests ───────────────────────────────────────────

class TestPydanticValidation:

    BASE = {
        "first_name": "Bob", "last_name": "Jones",
        "date_of_birth": "1975-11-22", "sex": "male",
        "phone_number": "5554443333", "address_line_1": "789 Pine Rd",
        "city": "Dallas", "state": "TX", "zip_code": "75201",
    }

    def test_valid_patient_create(self):
        from app.schemas.patient import PatientCreate
        p = PatientCreate(**self.BASE)
        assert p.first_name == "Bob"
        assert p.sex == "male"

    def test_sex_normalization(self):
        from app.schemas.patient import PatientCreate
        p = PatientCreate(**{**self.BASE, "sex": "M"})
        assert p.sex == "male"

    def test_phone_normalization(self):
        from app.schemas.patient import PatientCreate
        p = PatientCreate(**{**self.BASE, "phone_number": "(555) 444-3333"})
        assert p.phone_number == "5554443333"

    def test_invalid_email(self):
        from app.schemas.patient import PatientCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PatientCreate(**{**self.BASE, "email": "not-an-email"})

    def test_zip_plus_four(self):
        from app.schemas.patient import PatientCreate
        p = PatientCreate(**{**self.BASE, "zip_code": "75201-1234"})
        assert p.zip_code == "75201-1234"
