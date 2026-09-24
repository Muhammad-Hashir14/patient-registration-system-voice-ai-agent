import logging
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.services import conversation_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")

    logger.info(f"[VAPI] received message type: {msg_type}")

    # Only process conversation-update — this fires once per user turn with the final transcript
    # Ignore "transcript" events (partial/interim) to avoid duplicate processing
    if msg_type != "conversation-update":
        return {}

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
    session_id = f"vapi-{call_id}"

    logger.info(f"[VAPI] call={call_id} user said: {user_text}")

    result = conversation_service.process_message(
        db=db,
        session_id=session_id,
        user_message=user_text,
    )

    logger.info(f"[VAPI] call={call_id} agent response: {result['message']}")

    return {
        "messages": [
            {"role": "assistant", "content": result["message"]}
        ]
    }
