from pydantic import BaseModel
from typing import Any


class ConversationAnalysis(BaseModel):
    intents: list[str]
    extracted_fields: dict[str, Any]
    corrected_fields: dict[str, Any]
    user_question: str | None
    needs_clarification: bool
    clarification_reason: str | None
    uncertain_fields: list[str]  # fields where spelling may be uncertain
    registration_relevant: bool
    confirmation_response: str | None  # "yes" | "no" | None
    suggested_response: str
