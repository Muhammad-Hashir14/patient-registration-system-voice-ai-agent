import json
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.services import conversation_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    msg_type = body.get("message", {}).get("type", "")
    logger.info(f"[VAPI EVENT] type={msg_type}")
    return {}


@router.post("/vapi/end-call")
async def vapi_end_call(request: Request):
    """Called by the backend to signal Vapi to hang up."""
    return {"type": "end-call"}


@router.post("/vapi/chat")
async def vapi_chat(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        messages = body.get("messages", [])
        call_id = body.get("call", {}).get("id", "unknown")
        session_id = f"vapi-{call_id}"
        stream = body.get("stream", False)

        user_text = None
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "").strip()
                break

        if not user_text:
            reply = "I didn't catch that. Could you please repeat?"
        else:
            logger.info(f"[VAPI CHAT] session={session_id} user={user_text}")
            result = conversation_service.process_message(
                db=db,
                session_id=session_id,
                user_message=user_text,
            )
            reply = result["message"]
            logger.info(f"[VAPI CHAT] session={session_id} agent={reply}")

        if stream:
            return StreamingResponse(
                _stream_response(reply),
                media_type="text/event-stream",
            )
        return _chat_response(reply)

    except Exception as e:
        logger.error(f"[VAPI CHAT ERROR] {e}", exc_info=True)
        reply = "I'm sorry, I had a technical issue. Could you please repeat that?"
        if body.get("stream", False):
            return StreamingResponse(
                _stream_response(reply),
                media_type="text/event-stream",
            )
        return _chat_response(reply)


async def _stream_response(content: str):
    """Yield OpenAI-compatible SSE chunks then a [DONE] event."""
    chunk = {
        "id": "chatcmpl-vapi",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(chunk)}\n\n"
    done_chunk = {
        "id": "chatcmpl-vapi",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done_chunk)}\n\n"
    yield "data: [DONE]\n\n"


def _chat_response(content: str) -> dict:
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
