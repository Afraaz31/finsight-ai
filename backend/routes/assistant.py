"""Level 12: one chat for all uploaded files. The Orchestrator decides which agent works."""
from fastapi import APIRouter

from backend.agents import orchestrator
from backend.routes import _guarded
from backend.routes.uploads import json_safe
from backend.schemas.api_schemas import AssistantAnswer, AssistantAskRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswer)
def ask(request: AssistantAskRequest) -> dict:
    """Ask in plain English. The Orchestrator calls the Spreadsheet Agent (Excel/CSV), the Document
    Agent (PDF/Word/TXT) or both, and combines their findings. No doc_ids -> all uploaded files."""
    _guarded.before(request.question)
    result = orchestrator.ask(request.question, request.doc_ids, sheet=request.sheet, use_cache=request.use_cache)
    return json_safe(_guarded.after({**result, "route": "orchestrator"}))
