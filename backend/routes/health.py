"""GET /health and GET /companies: is the system ready, and what does it cover?"""
from fastapi import APIRouter

from backend.companies import COMPANIES
from backend.config import (GEMINI_API_KEY, GEMINI_FALLBACK_MODELS, GEMINI_MODEL, OLLAMA_ENABLED,
                            SEC_COLLECTION)
from backend.schemas.api_schemas import Company, HealthResponse
from backend.services.rag_service import available_years
from backend.services.retrieval_service import get_or_create_collection
from backend.services.upload_service import list_uploads

router = APIRouter(tags=["system"])


def sec_chunk_count() -> int:
    return get_or_create_collection(SEC_COLLECTION).count()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Readiness check. Never calls Gemini, so it costs no quota."""
    problems = []
    chunks = sec_chunk_count()
    if chunks == 0:
        problems.append("SEC vector store is empty: run python -m ingestion.build_vectorstore")
    key_ok = bool(GEMINI_API_KEY) and "your_" not in GEMINI_API_KEY
    if not key_ok:
        problems.append("GEMINI_API_KEY is not set in .env")
    return HealthResponse(
        status="ok" if not problems else "degraded",
        sec_chunks=chunks,
        uploads=len(list_uploads()),
        llm_model=GEMINI_MODEL,
        fallback_models=GEMINI_FALLBACK_MODELS,
        ollama_enabled=OLLAMA_ENABLED,
        api_key_configured=key_ok,
        problems=problems,
    )


@router.get("/companies", response_model=list[Company], tags=["sec"])
def companies() -> list[Company]:
    """The supported companies and the fiscal years we have reports for."""
    return [Company(ticker=t, name=c["name"], cik=c["cik"], fiscal_years=available_years(t))
            for t, c in COMPANIES.items()]
