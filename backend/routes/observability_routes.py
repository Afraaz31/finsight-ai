"""Level 13: read the traces. Used by the Monitoring page (and handy with curl during a demo)."""
from fastapi import APIRouter, Query

from backend import observability as obs
from backend.config import DAILY_LLM_CALL_LIMIT, RATE_LIMIT_PER_MINUTE

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/summary")
def summary() -> dict:
    """Requests, latency (avg / p50 / p95), cache hit rate, AI calls and tokens per model,
    fallbacks, guardrail actions, and AI calls used today vs the daily budget."""
    return {**obs.summary(), "daily_llm_call_limit": DAILY_LLM_CALL_LIMIT,
            "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE}


@router.get("/traces")
def traces(limit: int = Query(50, ge=1, le=500), request_id: str | None = None,
           questions_only: bool = True) -> list[dict]:
    """The most recent request traces (newest first), or one trace by its request id.
    questions_only=false also includes page loads (GET /companies, /financials ...)."""
    items = obs.load_traces(5000)
    if request_id:
        return [t for t in items if t.get("request_id") == request_id]
    if questions_only:
        items = [t for t in items if obs.is_question(t)]
    return list(reversed(items))[:limit]
