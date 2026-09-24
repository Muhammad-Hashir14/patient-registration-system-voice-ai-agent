import json
import logging
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.services import conversation_service
from app.database.connection import SessionLocal

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/vapi")
async def vapi_webhook(request: Request):
    body = await request.json()
    msg_type = body.get("message", {}).get("type", "")
    logger.info(f"[VAPI EVENT] type={msg_type}")
    return {}


@router.post("/vapi/end-call")
async def vapi_end_call(request: Request):
    """Called by the backend to signal Vapi to hang up."""
    return {"type": "end-call"}


@router.post("/vapi/chat")
@router.post("/vapi/chat/completions")
async def vapi_chat(request: Request):
    body = await request.json()
    logger.info(f"[VAPI CHAT RAW] {json.dumps(body)[:500]}")

    messages = body.get("messages", [])
    call_id = body.get("call", {}).get("id") or body.get("callId", "unknown")
    session_id = f"vapi-{call_id}"

    user_text = None
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = m.get("content", "").strip()
            break

    logger.info(f"[VAPI MESSAGES] roles={[m.get('role') for m in messages]} user_text={user_text!r}")

    return StreamingResponse(
        _process_and_stream(session_id, user_text),
        media_type="text/event-stream",
    )


async def _process_and_stream(session_id: str, user_text: str | None):
    # Yield empty delta immediately so Vapi sees connection alive (prevents timeout)
    empty = {
        "id": "chatcmpl-vapi",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(empty)}\n\n"

    try:
        if not user_text:
            reply = "I didn't catch that. Could you please repeat?"
        else:
            logger.info(f"[VAPI CHAT] session={session_id} user={user_text}")

            def _run():
                db = SessionLocal()
                try:
                    return conversation_service.process_message(
                        db=db, session_id=session_id, user_message=user_text
                    )
                finally:
                    db.close()

            result = await asyncio.get_event_loop().run_in_executor(None, _run)
            reply = result["message"]
            logger.info(f"[VAPI CHAT] session={session_id} agent={reply}")
    except Exception as e:
        logger.error(f"[VAPI CHAT ERROR] {e}", exc_info=True)
        reply = "I'm sorry, I had a technical issue. Could you please repeat that?"

    async for chunk in _stream_response(reply):
        yield chunk


async def _stream_response(content: str):
    """Yield OpenAI-compatible SSE chunks word by word, then [DONE]."""
    words = content.split(" ")
    for i, word in enumerate(words):
        text = word if i == len(words) - 1 else word + " "
        chunk = {
            "id": "chatcmpl-vapi",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}],
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
