from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from core.orchestrator import orchestrator


router = APIRouter()


class ChatRequest(BaseModel):

    user_id: str

    message: str

    conversation_id: Optional[str] = None

    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    agent: str
    strategy: Dict[str, Any]
    scoring: Optional[Dict[str, Any]] = None
    execution_time: float
    status: str


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):

    try:

        result = await orchestrator.process_user_input(

            user_input=request.message,

            user_id=request.user_id,

            conversation_id=request.conversation_id,

            metadata=request.metadata

        )

        return ChatResponse(
            response=result["response"],
            agent=result["agent"],
            strategy=result["strategy"],
            scoring=result.get("scoring"),
            execution_time=result["execution_time"],
            status=result["status"]
        )

    except Exception as e:

        raise HTTPException(

            status_code=500,

            detail=str(e)
        )
