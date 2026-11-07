"""FinSight AI - FastAPI application.

Run from the project root:   uvicorn backend.main:app --reload --port 8000
Interactive docs:            http://127.0.0.1:8000/docs
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend.routes import chat, financials, health, uploads
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


# ---------- request logging ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code,
             (time.perf_counter() - start) * 1000)
    return response


# ---------- errors -> proper HTTP status codes ----------
def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


@app.exception_handler(UploadNotFound)
async def not_found(_request: Request, exc: UploadNotFound):
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
    return _error(500, "Internal server error. Check the server log.")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
