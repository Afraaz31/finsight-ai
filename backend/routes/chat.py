"""POST /chat: ask about the 5 SEC companies. The route only calls the service (no logic here)."""
from fastapi import APIRouter

from backend.routes import _guarded
from backend.schemas.api_schemas import ChatRequest, ChatResponse
from backend.services.chat_service import answer_chat

router = APIRouter(tags=["sec"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    """Question -> grounded answer with cited SEC sources.

    Errors: 400 blocked by a guardrail, 422 bad input, 503 when the LLM or the vector store is unavailable.
    """
    _guarded.before(request.question)
    return _guarded.after(answer_chat(request.question, ticker=request.ticker, use_cache=request.use_cache))
