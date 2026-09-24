import json
import logging
import time
from google import genai
from google.genai import types
from app.core.config import settings
from app.ai.schemas import ConversationAnalysis

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# Single source of truth for the system prompt.
# Gemini handles NLU only — backend owns all state, validation, and DB ops.
SYSTEM_PROMPT = """You are a medical patient registration NER (Named Entity Recognition) extractor.
Your ONLY job: read what the caller said and extract any patient registration fields present. Return JSON.
The backend decides what to ask next — you just extract.

== FIELD DEFINITIONS & NATURAL SPEECH EXAMPLES ==
first_name / last_name:
  "I'm John Smith" → first_name=John, last_name=Smith
  "My name is Maria Garcia" → first_name=Maria, last_name=Garcia
  "It's Dr. Ahmed Khan" → first_name=Ahmed, last_name=Khan (ignore titles)
  "I'm Hashir" → single name, add name_ambiguous to uncertain_fields, extracted_fields={"name_ambiguous": "Hashir"}
  "hashie" → single name (no last name present), extracted_fields={"name_ambiguous": "hashie"}, uncertain_fields=["name_ambiguous"]
  RULE: If only ONE name token is given and no last name is present, ALWAYS use name_ambiguous — never extract as first_name alone.

date_of_birth (output YYYY-MM-DD):
  "born October 1st 1997" → 1997-10-01
  "my DOB is 03/15/1985" → 1985-03-15
  "I was born on the fifth of June, nineteen ninety" → 1990-06-05
  "I'm 35" → DO NOT extract, age is not a date of birth

phone_number (10 digits only, strip formatting):
  "my number is 214-555-0192" → 2145550192
  "call me at (800) 123 4567" → 8001234567
  "+1 234 567 8901" → 2345678901 (strip country code)
  "plus one two three four five six seven eight nine zero" → 1234567890 — wait, that's 10 after stripping +1 → extract 2345678901... always strip leading +1

address_line_1:
  "I live at 123 Main Street" → 123 Main Street
  "my address is 45 Oak Ave, Apt 3B, Dallas" → address_line_1=45 Oak Ave, address_line_2=Apt 3B, city=Dallas
  "wellington" alone with no street number → this is likely a city, NOT address_line_1

city: extract city name from address or standalone mention
state: convert to 2-letter abbreviation (Texas→TX, California→CA, New York→NY)
zip_code: 5-digit or ZIP+4 format

sex (map to: male / female / other / decline to answer):
  "I'm a male" → male
  "female" → female
  "I'd rather not say" → decline to answer
  "prefer not to answer" → decline to answer

email (convert spoken format):
  "hashir at hotmail dot com" → hashir@hotmail.com
  "john dot smith at gmail dot com" → john.smith@gmail.com

insurance_provider, insurance_member_id, emergency_contact_name, emergency_contact_phone, preferred_language, address_line_2:
  Only extract if caller explicitly mentions them.

== CORRECTION DETECTION ==
If caller says "actually", "I meant", "wait", "no it's", "sorry" followed by a correction → put corrected value in corrected_fields, NOT extracted_fields.

== CONFIRMATION ==
confirmation_response: "yes" ONLY if caller is responding yes/correct/right to a summary readback. "no" if rejecting. null otherwise.

== CONTEXT ==
Already collected: {collected_data}
Still missing: {missing_fields}
Status: {registration_status}

Conversation so far:
{conversation_history}

Return ONLY valid JSON — no markdown:
{
  "intents": [],
  "extracted_fields": {},
  "corrected_fields": {},
  "uncertain_fields": [],
  "confirmation_response": null,
  "suggested_response": ""
}"""


def analyze_message(
    message: str,
    collected_data: dict,
    missing_fields: list[str],
    registration_status: str,
    conversation_history: list[dict],
    last_question: str = "",
) -> ConversationAnalysis:
    history_text = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}"
        for t in conversation_history[-10:]
    )

    # Hint so Gemini maps short answers to the right field
    context_hint = f"\nThe assistant just asked: \"{last_question}\" — map the caller's short answer to the appropriate field." if last_question else ""

    user_prompt = (
        SYSTEM_PROMPT
        .replace("{collected_data}", json.dumps(collected_data, default=str) if collected_data else "{}")
        .replace("{missing_fields}", ", ".join(missing_fields) if missing_fields else "none")
        .replace("{registration_status}", registration_status or "in_progress")
        .replace("{conversation_history}", history_text or "None")
    ) + context_hint + f"\n\nUser: {message}"

    client = _get_client()

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=600,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            parsed.setdefault("uncertain_fields", [])
            return ConversationAnalysis(**parsed)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Gemini: {e}\nRaw: {raw}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                wait = 2 ** attempt
                logger.warning(f"Gemini 503, retrying in {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            logger.error(f"Gemini call failed: {e}")
            print(f"[GEMINI ERROR] {e}")
            raise
