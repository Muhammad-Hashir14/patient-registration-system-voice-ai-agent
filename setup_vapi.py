
"""
Run this script ONCE to:
1. Create/update Vapi assistant pointing to your local server
2. Print the phone number to call

Before running:
1. Start uvicorn:   uvicorn app.main:app --reload
2. Start tunnel:    cloudflared tunnel --url http://localhost:8000
3. Copy the URL from cloudflared output (e.g. https://abc-xyz.trycloudflare.com)
4. Run:             python setup_vapi.py https://abc-xyz.trycloudflare.com
"""
import sys
import requests

VAPI_API_KEY = "bc583003-676e-4bf9-93fc-f0b2210dfbee"
VAPI_BASE = "https://api.vapi.ai"

HEADERS = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}


def create_vapi_assistant(server_url: str) -> str:
    payload = {
        "name": "Patient Registration Agent",
        "firstMessage": "Hello! I'm your patient registration assistant. May I have your full name to get started?",
        "serverUrl": f"{server_url}/vapi",
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a patient registration assistant on a phone call. "
                        "Your backend handles all registration logic. "
                        "Keep responses short and clear — this is a voice call. "
                        "Do not repeat information the patient already gave."
                    )
                }
            ]
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
        "endCallMessage": "Your registration is complete. Goodbye!",
        "endCallPhrases": ["goodbye", "bye", "that's all", "done"],
    }

    resp = requests.get(f"{VAPI_BASE}/assistant", headers=HEADERS)
    assistants = resp.json() if resp.status_code == 200 else []
    existing = next((a for a in assistants if a.get("name") == "Patient Registration Agent"), None)

    if existing:
        assistant_id = existing["id"]
        requests.patch(f"{VAPI_BASE}/assistant/{assistant_id}", json=payload, headers=HEADERS)
        print(f"✅ Updated existing assistant: {assistant_id}")
    else:
        resp = requests.post(f"{VAPI_BASE}/assistant", json=payload, headers=HEADERS)
        if resp.status_code not in (200, 201):
            print(f"❌ Failed to create assistant: {resp.text}")
            return None
        assistant_id = resp.json()["id"]
        print(f"✅ Created assistant: {assistant_id}")

    return assistant_id


def get_phone_numbers() -> list:
    resp = requests.get(f"{VAPI_BASE}/phone-number", headers=HEADERS)
    return resp.json() if resp.status_code == 200 else []


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_vapi.py https://your-cloudflare-url.trycloudflare.com")
        print("\nSteps:")
        print("  1. Run: cloudflared tunnel --url http://localhost:8000")
        print("  2. Copy the https URL it prints")
        print("  3. Run: python setup_vapi.py <that-url>")
        return

    public_url = sys.argv[1].rstrip("/")
    print(f"Using server URL: {public_url}")

    assistant_id = create_vapi_assistant(public_url)
    if not assistant_id:
        return

    print("\n--- Phone Numbers on your Vapi account ---")
    numbers = get_phone_numbers()
    if numbers:
        for n in numbers:
            print(f"📞 {n.get('number')} — call this to test!")
    else:
        print("No phone numbers found.")
        print("→ Use the 'Talk' button at https://dashboard.vapi.ai to test via browser (free!)")

    print(f"\n✅ Server URL set to: {public_url}/vapi")
    print("✅ Go to https://dashboard.vapi.ai → find 'Patient Registration Agent' → click Talk")


if __name__ == "__main__":
    main()
