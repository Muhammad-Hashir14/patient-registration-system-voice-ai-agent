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


SYSTEM_PROMPT = """You are a patient registration assistant. Analyze the user message and return ONLY valid JSON.

Patient fields:
Required: first_name, last_name, date_of_birth (YYYY-MM-DD), sex (male/female/other/prefer not to say), phone_number, address_line_1, city, state, zip_code
Optional: email, address_line_2, insurance_provider, insurance_member_id, preferred_language, emergency_contact_name, emergency_contact_phone

Rules:
- Extract ALL fields mentioned in the message
- Put corrections (actually/I meant/wait) in corrected_fields
- Never guess — "I'm 35" does NOT give date_of_birth
- Keep suggested_response short (1-2 sentences), warm, professional
- confirmation_response: "yes" if confirming summary, "no" if rejecting, null otherwise

Return ONLY this JSON:
{
  "intents": ["greeting"|"provide_info"|"correction"|"question"|"confirmation"|"small_talk"|"unrelated"|"pause"],
  "extracted_fields": {},
  "corrected_fields": {},
  "user_question": null,
  "needs_clarification": false,
  "clarification_reason": null,
  "registration_relevant": true,
  "confirmation_response": null,
  "suggested_response": "..."
}"""


def analyze_message(
    message: str,
    collected_data: dict,
    missing_fields: list[str],
    registration_status: str,
    conversation_history: list[dict],
) -> ConversationAnalysis:
    # Last 4 turns only
    history_text = "\n".join(
        f"{t['role'].capitalize()}: {t['content']}"
        for t in conversation_history[-4:]
    )

    user_prompt = f"""Collected: {json.dumps(collected_data, default=str) or "{}"}
Missing: {", ".join(missing_fields) or "none"}
Status: {registration_status}
History:
{history_text or "None"}

User: {message}"""

    client = _get_client()

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=512,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        return ConversationAnalysis(**parsed)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from Gemini: {e}")
        raise ValueError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        print(f"[GEMINI ERROR] {e}")
        raise
