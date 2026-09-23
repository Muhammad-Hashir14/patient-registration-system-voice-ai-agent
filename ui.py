import streamlit as st
import requests
import uuid

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Patient Registration Agent", page_icon="🏥", layout="centered")
st.title("🏥 Patient Registration Assistant")

# ── Session state init ────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "collected_fields" not in st.session_state:
    st.session_state.collected_fields = {}
if "registration_status" not in st.session_state:
    st.session_state.registration_status = "in_progress"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Session")
    st.code(st.session_state.session_id, language=None)
    if st.button("🔄 New Session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.collected_fields = {}
        st.session_state.registration_status = "in_progress"
        st.rerun()

    st.subheader("Status")
    status = st.session_state.registration_status
    color = {"in_progress": "🟡", "pending_confirmation": "🔵", "completed": "🟢", "duplicate_found": "🔴"}.get(status, "⚪")
    st.write(f"{color} `{status}`")

    if st.session_state.collected_fields:
        st.subheader("Collected Fields")
        for k, v in st.session_state.collected_fields.items():
            st.write(f"**{k.replace('_', ' ').title()}:** {v}")

# ── Chat history ──────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ── Input ─────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Type your message..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/chat",
                    json={"session_id": st.session_state.session_id, "message": prompt},
                    timeout=60,
                )
                data = resp.json()
                if data.get("error"):
                    reply = f"⚠️ Error: {data['error']}"
                else:
                    reply = data["data"]["message"]
                    st.session_state.collected_fields = data["data"]["collected_fields"]
                    st.session_state.registration_status = data["data"]["registration_status"]
            except requests.exceptions.ConnectionError:
                reply = "⚠️ Cannot connect to the API. Make sure `uvicorn app.main:app --reload` is running."
            except Exception as e:
                reply = f"⚠️ Unexpected error: {e}"

        st.write(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

    st.rerun()
