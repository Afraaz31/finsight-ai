"""FinSight AI - FastAPI application.

Run from the project root:   uvicorn backend.main:app --reload --port 8000
Interactive docs:            http://127.0.0.1:8000/docs
"""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend import guardrails
from backend import observability as obs
from backend.routes import (assistant, chat, filings, financials, health, observability_routes, reports,
                            uploads)
from backend.services.filing_service import SectionNotFound
from backend.services.financial_service import UnknownCompany
from backend.services.llm_service import LLMError
from backend.services.table_service import PlanError
from backend.services.upload_service import UploadError, UploadNotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
log = logging.getLogger("finsight.api")


def warm_up() -> None:
    """Load the embedding model once at startup, so the first question isn't slow."""
    try:
        from backend.services.embedding_service import get_model
        get_model()
        log.info("Embedding model loaded.")
    except Exception as exc:   # the API still starts; /health will show what is missing
        log.warning("Could not pre-load the embedding model: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm_up()
    yield


app = FastAPI(
    title="FinSight AI API",
    description="Financial research chatbot: SEC 10-K RAG for 5 companies, plus your own uploaded files.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(uploads.router)
app.include_router(financials.router)
app.include_router(filings.router)
app.include_router(reports.router)
app.include_router(assistant.router)
app.include_router(observability_routes.router)


# ---------- Level 13: observability + rate limit, for every request ----------
EXPENSIVE = ("/chat", "/assistant/ask", "/uploads/ask", "/report/")   # these may call the AI
NOT_TRACED = ("/health", "/docs", "/openapi.json", "/", "/favicon.ico")


@app.middleware("http")
async def observe(request: Request, call_next):
    """Request id, a trace per request, timing, a structured log line, and the rate-limit guardrail."""
    request_id = request.headers.get("X-Request-ID") or obs.new_request_id()
    path = request.url.path
    if path.startswith("/observability") or path in NOT_TRACED:
        response = await call_next(request)          # don't trace the monitoring page itself
        response.headers["X-Request-ID"] = request_id
        return response
    obs.start_trace(request_id, request.method, path)
    client = request.client.host if request.client else "unknown"
    if path.startswith(EXPENSIVE) and guardrails.rate_limited(client):
        obs.record_guardrail("rate_limit", "blocked", f"more than {guardrails.RATE_LIMIT_PER_MINUTE}/min")
        obs.set_field("route", "blocked")
        obs.finish_trace(429)
        return JSONResponse(status_code=429, headers={"X-Request-ID": request_id, "Retry-After": "60"},
                            content={"detail": "Too many questions in one minute. Please wait a moment.",
                                     "guardrail": "rate_limit"})
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:                          # unhandled error: still finish (and keep) the trace
        obs.finish_trace(500, f"{type(exc).__name__}: {exc}"[:300])
        raise
    trace = obs.finish_trace(response.status_code)
    response.headers["X-Request-ID"] = request_id
    log.info(json.dumps({"request_id": request_id, "method": request.method, "path": path,
                         "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000),
                         "llm_calls": len(trace["llm_calls"]) if trace else 0,
                         "guardrails": [f"{g['name']}:{g['action']}" for g in (trace or {}).get("guardrails", [])
                                        if g["action"] != "passed"]}))
    return response


# ---------- errors -> proper HTTP status codes ----------
def _error(status_code: int, message: str) -> JSONResponse:
    obs.set_field("error", message[:300])            # Level 13: visible in the request's trace
    return JSONResponse(status_code=status_code, content={"detail": message})


@app.exception_handler(guardrails.GuardrailBlocked)
async def guardrail_blocked(_request: Request, exc: guardrails.GuardrailBlocked):
    return JSONResponse(status_code=400, content={"detail": str(exc), "guardrail": exc.name})


@app.exception_handler(UploadNotFound)
async def not_found(_request: Request, exc: UploadNotFound):
    return _error(404, str(exc))


@app.exception_handler(SectionNotFound)
async def section_not_found(_request: Request, exc: SectionNotFound):
    return _error(404, str(exc))


@app.exception_handler(UnknownCompany)
async def unknown_company(_request: Request, exc: UnknownCompany):
    return _error(404, str(exc))


@app.exception_handler(UploadError)
async def bad_upload(_request: Request, exc: UploadError):
    return _error(400, str(exc))


@app.exception_handler(PlanError)
async def bad_plan(_request: Request, exc: PlanError):
    return _error(422, str(exc))


@app.exception_handler(ValueError)
async def bad_value(_request: Request, exc: ValueError):
    return _error(400, str(exc))


@app.exception_handler(LLMError)
async def llm_unavailable(_request: Request, exc: LLMError):
    return _error(503, str(exc))


@app.exception_handler(RuntimeError)
async def not_ready(_request: Request, exc: RuntimeError):
    log.error("Not ready: %s", exc)
    return _error(503, str(exc))


@app.exception_handler(Exception)
async def unexpected(_request: Request, exc: Exception):
    log.exception("Unexpected error")          # full details go to the server log only
    obs.set_field("error", f"{type(exc).__name__}: {exc}"[:300])
    return _error(500, "Internal server error. Check the server log.")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
