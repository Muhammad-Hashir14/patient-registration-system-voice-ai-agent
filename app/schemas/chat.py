from pydantic import BaseModel
from typing import Any


class ConversationRequest(BaseModel):
    session_id: str
    message: str


class ConversationResponse(BaseModel):
    session_id: str
    message: str
    registration_status: str
    collected_fields: dict[str, Any]
