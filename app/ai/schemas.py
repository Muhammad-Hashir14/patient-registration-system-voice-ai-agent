from pydantic import BaseModel
from typing import Any


class ConversationAnalysis(BaseModel):
    intents: list[str] = []
    extracted_fields: dict[str, Any] = {}
    corrected_fields: dict[str, Any] = {}
    uncertain_fields: list[str] = []
    confirmation_response: str | None = None
    suggested_response: str = ""
