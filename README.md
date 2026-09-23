# Patient Registration AI Agent

A conversational AI agent for patient registration, built with FastAPI, Gemini, LangChain, and PostgreSQL (Neon).

---

## Project Overview

This is a **text-based conversational patient registration assistant**. Unlike a rigid form-filling chatbot, it understands natural language, handles information provided in any order, extracts multiple fields from a single message, detects corrections, and maintains conversation context across turns.

---

## Architecture

```
POST /chat
      ↓
ConversationService          ← orchestrates everything
      ↓
GeminiClient (LangChain)     ← NLU: intent, extraction, corrections, response
      ↓
RegistrationService          ← validation, state management, confirmation
      ↓
PatientService               ← database CRUD
      ↓
PostgreSQL (Neon)
```

**Key principle:** Gemini handles language understanding only. The backend owns all state mutations, validation, and database operations.

---

## Conversational Design

The agent follows this loop on every message:

**UNDERSTAND → RESPOND → EXTRACT → VALIDATE → UPDATE STATE → CONTINUE**

- Responds naturally to greetings, small talk, and questions
- Extracts all patient fields mentioned in a single message
- Detects and applies corrections ("actually, my last name is...")
- Never guesses — "I'm 35" does not produce a date of birth
- Redirects unrelated questions politely
- Reads back all collected data and asks for explicit confirmation before saving
- Only claims data was saved after a successful database write

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI |
| LLM | Google Gemini 1.5 Flash |
| LLM Orchestration | LangChain |
| Database | PostgreSQL via Neon |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic v2 |
| Server | Uvicorn |
| Testing | pytest |

---

## Setup Instructions

### 1. Clone and install dependencies

```bash
git clone <repo>
cd patient-registration-system-voice-ai-agent
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

### 3. Run the application

```bash
uvicorn app.main:app --reload
```

Tables are created automatically on startup via SQLAlchemy.

Swagger UI: http://localhost:8000/docs

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `DATABASE_URL` | PostgreSQL connection string (Neon or any PostgreSQL) |

---

## Neon PostgreSQL Setup

1. Create a free account at https://neon.tech
2. Create a new project and database
3. Copy the connection string from the Neon dashboard
4. Paste it as `DATABASE_URL` in your `.env` file
5. Ensure `?sslmode=require` is appended to the connection string

---

## Gemini Setup

1. Go to https://aistudio.google.com/app/apikey
2. Create an API key
3. Paste it as `GEMINI_API_KEY` in your `.env` file

---

## API Endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Send a message to the registration agent |

**Request:**
```json
{
  "session_id": "abc123",
  "message": "Hi, I'm John Smith and I live in Dallas."
}
```

**Response:**
```json
{
  "data": {
    "session_id": "abc123",
    "message": "Nice to meet you, John Smith! I see you're in Dallas. What's your date of birth?",
    "registration_status": "in_progress",
    "collected_fields": {
      "first_name": "John",
      "last_name": "Smith",
      "city": "Dallas"
    }
  },
  "error": null
}
```

`registration_status` values: `in_progress` | `pending_confirmation` | `completed` | `duplicate_found`

### Patients

| Method | Path | Description |
|--------|------|-------------|
| GET | `/patients` | List patients (filter by `last_name`, `date_of_birth`, `phone_number`) |
| GET | `/patients/{patient_id}` | Get a patient by ID |
| POST | `/patients` | Create a patient directly |
| PUT | `/patients/{patient_id}` | Update a patient |
| DELETE | `/patients/{patient_id}` | Soft delete a patient |

All responses use the format:
```json
{ "data": {}, "error": null }
```

---

## Database Schema

```sql
CREATE TABLE patients (
    patient_id          VARCHAR PRIMARY KEY,
    first_name          VARCHAR NOT NULL,
    last_name           VARCHAR NOT NULL,
    date_of_birth       DATE NOT NULL,
    sex                 VARCHAR NOT NULL,
    phone_number        VARCHAR NOT NULL,
    address_line_1      VARCHAR NOT NULL,
    address_line_2      VARCHAR,
    city                VARCHAR NOT NULL,
    state               VARCHAR NOT NULL,
    zip_code            VARCHAR NOT NULL,
    email               VARCHAR,
    insurance_provider  VARCHAR,
    insurance_member_id VARCHAR,
    preferred_language  VARCHAR,
    emergency_contact_name  VARCHAR,
    emergency_contact_phone VARCHAR,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at          TIMESTAMP WITH TIME ZONE
);

CREATE TABLE conversation_sessions (
    session_id              VARCHAR PRIMARY KEY,
    patient_data            JSON,
    conversation_history    JSON,
    registration_status     VARCHAR,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL
);
```

---

## Validation

Applied by the backend (not delegated to the LLM):

| Field | Rule |
|-------|------|
| `date_of_birth` | Valid date, not in the future, not before 1900 |
| `phone_number` | US 10-digit number (formatting stripped) |
| `zip_code` | US 5-digit or ZIP+4 format |
| `sex` | male / female / other / prefer not to say |
| `email` | Basic format check (optional field) |

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Gemini failure | Graceful fallback message; existing session state preserved |
| Invalid LLM output | Logged; fallback response returned |
| Validation failure | Error appended to response; invalid field not stored |
| Database failure | 500 response; no state corruption |
| Duplicate patient | `duplicate_found` status; user asked to confirm update |
| Patient not found | 404 response |
| Invalid session | New session created automatically |

Stack traces and secrets are never exposed in API responses.

---

## Testing

```bash
pytest tests/ -v
```

Test coverage includes:
- Greetings and small talk
- "Are you available?" / "Are you a human?"
- Unrelated questions (weather redirect)
- Single and multi-field extraction
- Out-of-order information
- Corrections ("actually, my last name is...")
- "Wait." / pause handling
- "I'm 35" — age not converted to DOB
- Invalid DOB (future date)
- Invalid phone number
- Invalid ZIP code
- Optional field decline
- Confirmation flow (yes/no)
- Duplicate phone detection
- Patient CRUD endpoints
- Gemini failure graceful degradation
- Pydantic validation unit tests

---

## Future Voice Integration

The `/chat` endpoint is designed to accept transcribed speech without modification:

```python
# Voice provider sends transcribed text to the same endpoint
POST /chat
{
  "session_id": "call-sid-from-twilio",
  "message": "transcribed speech text here"
}
```

To add voice support, connect a provider (Twilio, Vapi, Retell) that:
1. Receives a phone call
2. Transcribes speech to text (STT)
3. POSTs the text to `/chat`
4. Converts the response `message` to speech (TTS)
5. Plays it back to the caller

No changes to registration logic are required.

---

## Limitations

- Session state is stored in PostgreSQL; very long conversations may accumulate large history JSON
- Gemini context window is limited to the last 10 conversation turns
- Duplicate detection uses phone number only
- No authentication or rate limiting (add before production)
- Date parsing relies on `python-dateutil`; ambiguous dates (e.g., "01/02/03") may be misinterpreted
