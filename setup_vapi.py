"""
Run this script whenever you want to sync Vapi assistant settings.
The Railway URL is fixed — no argument needed.

Usage:
    python setup_vapi.py
"""
import requests

VAPI_API_KEY = "bc583003-676e-4bf9-93fc-f0b2210dfbee"
VAPI_BASE = "https://api.vapi.ai"
RAILWAY_URL = "https://web-production-82a93.up.railway.app"

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

# Vapi assistant config.
# We use serverUrl as a custom LLM endpoint so ALL conversation logic
# runs through our backend (Gemini + registration service).
# Vapi handles only STT and TTS — our /vapi endpoint drives the conversation.
ASSISTANT_PAYLOAD = {
    "name": "Patient Registration Agent",
    "firstMessage": (
        "Hello! I'm your patient registration assistant. "
        "Are you calling to register as a new patient, look up your existing information, or update your record?"
    ),
    "serverUrl": f"{RAILWAY_URL}/vapi",
    "model": {
        "provider": "custom-llm",
        "url": f"{RAILWAY_URL}/vapi/chat",
        "model": "gemini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a patient registration assistant. "
                    "Keep all responses under 2 sentences. "
                    "This is a voice call — be warm, clear, and concise."
                ),
            }
        ],
    },
    "voice": {
        "provider": "vapi",
        "voiceId": "Elliot",
    },
    "transcriber": {
        "provider": "deepgram",
        "model": "nova-2",
        "language": "en",
    },
    "endCallMessage": "Thank you. Goodbye!",
    "endCallPhrases": ["goodbye", "bye", "thank you goodbye", "that's all"],
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 600,
}


def sync_assistant() -> str | None:
    resp = requests.get(f"{VAPI_BASE}/assistant", headers=HEADERS)
    assistants = resp.json() if resp.status_code == 200 else []
    existing = next((a for a in assistants if a.get("name") == "Patient Registration Agent"), None)

    if existing:
        assistant_id = existing["id"]
        r = requests.patch(f"{VAPI_BASE}/assistant/{assistant_id}", json=ASSISTANT_PAYLOAD, headers=HEADERS)
        if r.status_code not in (200, 201):
            print(f"❌ Failed to update assistant: {r.text}")
            return None
        print(f"✅ Updated assistant: {assistant_id}")
    else:
        r = requests.post(f"{VAPI_BASE}/assistant", json=ASSISTANT_PAYLOAD, headers=HEADERS)
        if r.status_code not in (200, 201):
            print(f"❌ Failed to create assistant: {r.text}")
            return None
        assistant_id = r.json()["id"]
        print(f"✅ Created assistant: {assistant_id}")

    return assistant_id


def get_phone_numbers() -> list:
    resp = requests.get(f"{VAPI_BASE}/phone-number", headers=HEADERS)
    return resp.json() if resp.status_code == 200 else []


def main():
    print(f"Syncing Vapi assistant → {RAILWAY_URL}")
    assistant_id = sync_assistant()
    if not assistant_id:
        return

    print("\n--- Phone Numbers ---")
    numbers = get_phone_numbers()
    if numbers:
        for n in numbers:
            print(f"📞 {n.get('number')} — call this to test!")
    else:
        print("No phone numbers. Use the Talk button at https://dashboard.vapi.ai")

    print(f"\n✅ Server URL: {RAILWAY_URL}/vapi")
    print("✅ Go to https://dashboard.vapi.ai → Patient Registration Agent → Talk")


if __name__ == "__main__":
    main()
