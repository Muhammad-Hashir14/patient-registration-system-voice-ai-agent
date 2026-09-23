from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.services import conversation_service

router = APIRouter()


@router.post("/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")

    # Vapi calls this on every user utterance
    if msg_type in ("transcript", "conversation-update"):
        # Get the latest user message from the conversation
        artifact = message.get("artifact", {})
        messages = artifact.get("messages", [])

        # Find the last user message
        user_text = None
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("message") or m.get("content", "")
                break

        if not user_text:
            return {}

        call_id = message.get("call", {}).get("id", "unknown")

        result = conversation_service.process_message(
            db=db,
            session_id=f"vapi-{call_id}",
            user_message=user_text,
        )

        return {
            "messages": [
                {"role": "assistant", "content": result["message"]}
            ]
        }

    # Handle end-of-call
    if msg_type == "end-of-call-report":
        return {}

    return {}
