"""Talks to the FinSight FastAPI backend over HTTP. The UI never imports backend code directly.

Every function returns the JSON from the API or raises ApiError with a message you can show.
"""
import os

import requests

API_URL = os.getenv("FINSIGHT_API_URL", "http://127.0.0.1:8000").rstrip("/")
PUBLIC_DEMO = os.getenv("PUBLIC_DEMO", "false").lower() == "true"   # the live demo: sample files only
QUICK_TIMEOUT = 10        # health, lists
ANSWER_TIMEOUT = 330      # a question may fall back to Ollama on CPU (up to ~300 s)


class ApiError(Exception):
    def __init__(self, status: int, message: str, guardrail: str | None = None):
        if guardrail:   # Level 13: a guardrail refused the request -> say which one
            message = f"🛡️ {message} (guardrail: {guardrail.replace('_', ' ')})"
        super().__init__(message)
        self.status, self.message, self.guardrail = status, message, guardrail


def _detail(response: requests.Response) -> tuple[str, str | None]:
    """FastAPI puts the reason in "detail" (a string, or a list of field errors for 422).
    Level 13: a guardrail refusal also names the guardrail."""
    try:
        body = response.json()
        detail = body.get("detail", response.text)
    except (ValueError, AttributeError):
        return response.text or f"HTTP {response.status_code}", None
    if isinstance(detail, list):   # 422 validation errors
        return "; ".join(str(d.get("msg", d)).replace("Value error, ", "") for d in detail), None
    return str(detail), body.get("guardrail")


def _call(method: str, path: str, timeout: int = QUICK_TIMEOUT, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=timeout, **kwargs)
    except requests.ConnectionError:
        raise ApiError(0, f"Can't reach the FinSight API at {API_URL}. Start it with: "
                          "uvicorn backend.main:app --port 8000")
    except requests.Timeout:
        raise ApiError(0, "The API took too long to answer. Try again.")
    if response.status_code >= 400:
        raise ApiError(response.status_code, *_detail(response))
    return response.json() if response.content else None


def health() -> dict:
    return _call("GET", "/health")


def companies() -> list[dict]:
    return _call("GET", "/companies")


def chat(question: str, ticker: str | None, use_cache: bool) -> dict:
    return _call("POST", "/chat", timeout=ANSWER_TIMEOUT,
                 json={"question": question, "ticker": ticker, "use_cache": use_cache})


def upload(filename: str, data: bytes) -> dict:
    return _call("POST", "/uploads", timeout=120, files={"file": (filename, data)})


def list_uploads() -> list[dict]:
    return _call("GET", "/uploads")


def ask_uploads(question: str, doc_ids: list[str], sheet: str | None, use_cache: bool) -> dict:
    return _call("POST", "/uploads/ask", timeout=ANSWER_TIMEOUT,
                 json={"question": question, "doc_ids": doc_ids, "sheet": sheet, "use_cache": use_cache})


def delete_upload(doc_id: str) -> None:
    _call("DELETE", f"/uploads/{doc_id}")


# ---------- Level 7: exact SEC figures ----------
def metrics() -> list[dict]:
    return _call("GET", "/metrics")


def financials(ticker: str) -> dict:
    return _call("GET", f"/financials/{ticker}")


def compare(tickers: list[str], metric: str, fiscal_year: int | None) -> dict:
    return _call("POST", "/compare", json={"tickers": tickers, "metric": metric, "fiscal_year": fiscal_year})


# ---------- Level 10: full 10-K sections ----------
def section(ticker: str, fiscal_year: int, section_id: str) -> dict:
    return _call("GET", "/sec/section", params={"ticker": ticker, "fiscal_year": fiscal_year,
                                                 "section_id": section_id})


# ---------- Level 13: observability ----------
def observability_summary() -> dict:
    return _call("GET", "/observability/summary")


def observability_traces(limit: int = 50) -> list[dict]:
    return _call("GET", "/observability/traces", params={"limit": limit})


# ---------- Level 12: the Orchestrator ----------
def ask_assistant(question: str, doc_ids: list[str], sheet: str | None, use_cache: bool) -> dict:
    """Level 12: the Orchestrator (Spreadsheet Agent + Document Agent)."""
    return _call("POST", "/assistant/ask", timeout=ANSWER_TIMEOUT,
                 json={"question": question, "doc_ids": doc_ids, "sheet": sheet, "use_cache": use_cache})
