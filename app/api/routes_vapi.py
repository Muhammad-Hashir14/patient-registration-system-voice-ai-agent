import logging
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.services import conversation_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles Vapi server-side events (call start, end, status updates)."""
    body = await request.json()
    message = body.get("message", {})
    msg_type = message.get("type", "")
    logger.info(f"[VAPI EVENT] type={msg_type}")
    return {}


@router.post("/vapi/chat")
async def vapi_chat(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        messages = body.get("messages", [])
        call_id = body.get("call", {}).get("id", "unknown")
        session_id = f"vapi-{call_id}"

        user_text = None
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "").strip()
                break

        if not user_text:
            return _chat_response("I didn't catch that. Could you please repeat?")

        logger.info(f"[VAPI CHAT] session={session_id} user={user_text}")

        result = conversation_service.process_message(
            db=db,
            session_id=session_id,
            user_message=user_text,
        )

        reply = result["message"]
        logger.info(f"[VAPI CHAT] session={session_id} agent={reply}")
        return _chat_response(reply)

    except Exception as e:
        logger.error(f"[VAPI CHAT ERROR] {e}", exc_info=True)
        return _chat_response("I'm sorry, I had a technical issue. Could you please repeat that?")


def _chat_response(content: str) -> dict:
    """Returns OpenAI-compatible chat completion response."""
    return {
        "id": "chatcmpl-vapi",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
