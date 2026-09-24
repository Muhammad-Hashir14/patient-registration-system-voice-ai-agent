# Patient Registration Voice AI Agent

A voice-enabled conversational AI agent that registers patients over a phone call. Built with FastAPI, Groq (LLaMA/Qwen), Vapi, and PostgreSQL.

---

## What It Does

Patients call a phone number, speak naturally, and the agent collects all required registration information through conversation — handling corrections, out-of-order input, and ambiguous responses. Once confirmed, the record is saved to the database and the call ends automatically.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI + Uvicorn |
| LLM (NER extraction) | Groq — `qwen/qwen3.8-27b` |
| Voice Platform | Vapi (STT + TTS + phone) |
| Speech-to-Text | Deepgram Nova-2 (via Vapi) |
| Text-to-Speech | Vapi Elliot voice |
| Database | PostgreSQL via Neon |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic v2 |
| Deployment | Railway |

---

## Architecture

```
Phone Call
    ↓
Vapi (STT → text)
    ↓
POST /vapi/chat/completions   ← custom LLM endpoint
    ↓
ConversationService           ← orchestrates everything
    ↓
Groq (Qwen)                   ← NER extraction only
    ↓
RegistrationService           ← validation, state, confirmation
    ↓
PatientService                ← database CRUD
    ↓
PostgreSQL (Neon)
```

Groq handles language understanding only. The backend owns all state, validation, and database operations.

---

## Setup

### 1. Clone and install

```bash
git clone <repo>
cd patient-registration-system-voice-ai-agent
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
VAPI_API_KEY=your_vapi_private_api_key
RAILWAY_URL=https://your-app.up.railway.app
```

### 3. Run locally

```bash
uvicorn app.main:app --reload
```

Swagger UI: http://localhost:8000/docs

### 4. Set up Vapi assistant

After deploying to Railway (or with a tunnel like ngrok for local), run:

```bash
python setup_vapi.py
```

This creates (or recreates) the Vapi assistant pointed at your `RAILWAY_URL`. It prints the phone number to call for testing.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key — get one at https://console.groq.com |
| `DATABASE_URL` | PostgreSQL connection string |
| `VAPI_API_KEY` | Vapi private API key — from https://dashboard.vapi.ai |
| `RAILWAY_URL` | Your deployed app URL (used by Vapi as the custom LLM base URL) |

> For Railway deployment, add all four variables under Settings → Variables in your Railway project.

---

## Services Used

### Groq
Fast LLM inference. Used for named entity recognition — extracting patient fields from natural speech. Model: `qwen/qwen3.8-27b`. Typical response time ~150ms.
Get API key: https://console.groq.com

### Vapi
Voice AI platform. Handles the phone call, speech-to-text (Deepgram), and text-to-speech. Sends transcribed text to our custom LLM endpoint and speaks the response back.
Get API key: https://dashboard.vapi.ai

### Neon
Serverless PostgreSQL. Stores patient records and conversation sessions.
Get connection string: https://neon.tech

### Railway
Cloud deployment platform. Hosts the FastAPI app.
Deploy: https://railway.app

---

## API Endpoints

### Voice (Vapi)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/vapi/chat/completions` | Custom LLM endpoint called by Vapi each turn |
| POST | `/vapi` | Vapi webhook (call events) |

### Chat (text, for testing)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Send a text message to the registration agent |

**Request:**
```json
{ "session_id": "test-123", "message": "Hi, I'm John Smith" }
```

**Response:**
```json
{
  "data": {
    "session_id": "test-123",
    "message": "Got it, first name John. Last name Smith. What is your date of birth?",
    "registration_status": "in_progress",
    "collected_fields": { "first_name": "John", "last_name": "Smith" }
  },
  "error": null
}
```

`registration_status`: `in_progress` | `pending_confirmation` | `completed` | `duplicate_found`

### Patients (CRUD)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/patients` | List patients (filter by `last_name`, `date_of_birth`, `phone_number`) |
| GET | `/patients/{id}` | Get patient by ID |
| POST | `/patients` | Create patient directly |
| PUT | `/patients/{id}` | Update patient |
| DELETE | `/patients/{id}` | Soft delete patient |

---

## Conversation Flow

```
UNDERSTAND → EXTRACT → VALIDATE → UPDATE STATE → RESPOND
```

- Extracts all fields mentioned in a single message
- Handles corrections ("actually my last name is...")
- Single-word names trigger first/last name disambiguation
- Reads back all data and asks for confirmation before saving
- Ends the call automatically after successful registration

---

## Validation Rules

| Field | Rule |
|-------|------|
| `date_of_birth` | Valid date, not future, not before 1900 |
| `phone_number` | US 10-digit (strips `+1`, formatting, spoken "plus one") |
| `zip_code` | US 5-digit or ZIP+4 |
| `sex` | male / female / other / decline to answer |
| `state` | Valid 2-letter US abbreviation |
| `email` | Basic format check (optional) |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
app/
├── ai/
│   ├── gemini_client.py     # Groq LLM client + prompt
│   └── schemas.py           # ConversationAnalysis schema
├── api/
│   ├── routes_chat.py       # Text chat endpoint
│   ├── routes_patients.py   # Patient CRUD endpoints
│   └── routes_vapi.py       # Vapi custom LLM + webhook
├── core/
│   └── config.py            # Settings from .env
├── models/                  # SQLAlchemy models
├── schemas/                 # Pydantic schemas
├── services/
│   ├── conversation_service.py   # Main conversation logic
│   ├── registration_service.py   # Validation + state
│   └── patient_service.py        # DB operations
└── utils/
    └── validation.py        # Field validators
setup_vapi.py                # Vapi assistant setup script
```
