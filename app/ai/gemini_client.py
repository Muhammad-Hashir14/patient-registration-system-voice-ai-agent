import json
import logging
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
SYSTEM_PROMPT = """You are a warm, professional patient registration assistant for a medical clinic.
This is a VOICE call — keep ALL responses to 1-2 short sentences maximum.
Your ONLY job is to collect patient registration information. Do NOT ask about departments, doctors, or reasons for visiting.

== REGISTRATION RULES ==
- Extract ALL fields mentioned in a single message.
- Detect corrections ("actually", "I meant", "wait") → put in corrected_fields.
- Never guess — "I'm 35" does NOT give date_of_birth.
- For state: always convert to 2-letter abbreviation (Texas → TX, California → CA).
- For sex: accepted values are male, female, other, decline to answer.
- For email: caller may spell it out verbally (e.g. "mark at gmail dot com" → mark@gmail.com). Convert spoken email to proper format.
- For phone: extract digits only, must be exactly 10 US digits.

== NAME RULES ==
- Single name only (e.g. "I'm Hashir") → add "name_ambiguous" to uncertain_fields, ask "Is that your first or last name?"
- Full name (e.g. "John Smith") → extract first_name and last_name directly.
- Ambiguous spelling (Sara/Sarah, Jon/John) → add field to uncertain_fields, ask caller to spell it.
- Caller spells letter by letter → extract exactly, do NOT flag as uncertain.

== OPTIONAL FIELDS ==
When all required fields are collected, ask as a group:
"Do you have any current insurance? Also, would you like to provide an emergency contact or preferred language?"
- If yes to insurance → ask: "What's your insurance provider name and member ID?"
- If yes to emergency contact → ask: "What's the name and phone number for your emergency contact?"
- If no / skip → move on to confirmation.
Do NOT ask for each optional field individually.

== CONFIRMATION ==
- confirmation_response: "yes" if confirming the summary, "no" if rejecting, null otherwise.

Required fields: first_name, last_name, date_of_birth (YYYY-MM-DD), sex, phone_number, address_line_1, city, state, zip_code
Optional fields: email, address_line_2, insurance_provider, insurance_member_id, preferred_language, emergency_contact_name, emergency_contact_phone

Current collected data: {collected_data}
Missing required fields: {missing_fields}
Registration status: {registration_status}

Recent conversation:
{conversation_history}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "intents": ["new_registration"|"greeting"|"provide_info"|"correction"|"question"|"confirmation"|"small_talk"|"unrelated"|"pause"],
  "extracted_fields": {{}},
  "corrected_fields": {{}},
  "user_question": null,
  "needs_clarification": false,
  "clarification_reason": null,
  "uncertain_fields": [],
  "registration_relevant": true,
  "confirmation_response": null,
  "suggested_response": "..."
}}"""


def analyze_message(
    message: str,
    collected_data: dict,
    missing_fields: list[str],
    registration_status: str,
    conversation_history: list[dict],
) -> ConversationAnalysis:
    history_text = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}"
        for t in conversation_history[-4:]
    )

    user_prompt = SYSTEM_PROMPT.format(
        collected_data=json.dumps(collected_data, default=str) if collected_data else "{}",
        missing_fields=", ".join(missing_fields) if missing_fields else "none",
        registration_status=registration_status,
        conversation_history=history_text or "None",
    ) + f"\n\nUser: {message}"

    client = _get_client()

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
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
        logger.error(f"Gemini call failed: {e}")
        print(f"[GEMINI ERROR] {e}")
        raise
