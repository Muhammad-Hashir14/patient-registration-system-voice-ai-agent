from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.schemas.chat import ConversationRequest, ConversationResponse
from app.services import conversation_service

router = APIRouter()


@router.post("/chat", response_model=dict)
def chat(request: ConversationRequest, db: Session = Depends(get_db)):
    try:
        result = conversation_service.process_message(
            db=db,
            session_id=request.session_id,
            user_message=request.message,
        )
        return {"data": result, "error": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"data": None, "error": str(e)})
