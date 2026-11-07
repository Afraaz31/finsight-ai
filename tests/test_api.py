"""Level 5 tests: the FastAPI endpoints, with FastAPI's TestClient.

No server needs to be running and no quota is used: the LLM-calling services are replaced by fakes,
and uploads go to a temporary folder. TestClient is created WITHOUT "with", so the startup
warm-up (loading the embedding model) is skipped.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import chat as chat_route
from backend.routes import health as health_route
from backend.routes import uploads as uploads_route
from backend.services import upload_service
from backend.services.llm_service import LLMError

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
client = TestClient(app, raise_server_exceptions=False)

FAKE_CHAT = {"answer": "NVIDIA depends on a few manufacturers [1].",
             "sources": [{"number": 1, "company": "NVIDIA Corporation", "ticker": "NVDA", "fiscal_year": 2026,
                          "period_end": "2026-01-25", "section": "Item 1A. Risk Factors",
                          "document_url": "https://www.sec.gov/x.htm", "score": 0.61, "excerpt": "..."}],
             "companies": ["NVDA"], "used_llm": True, "model": "fake-model", "cached": False,
             "retrieved_chunks": 5}


@pytest.fixture
def uploads_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(upload_service, "_index_text", lambda doc_id, filename, pages: len(pages))


# ---------- system ----------
def test_health(monkeypatch):
    monkeypatch.setattr(health_route, "sec_chunk_count", lambda: 4321)
    body = client.get("/health").json()
    assert body["sec_chunks"] == 4321
    assert {"status", "llm_model", "fallback_models", "ollama_enabled", "problems"} <= body.keys()


def test_companies():
    body = client.get("/companies").json()
    assert [c["ticker"] for c in body] == ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"]


def test_docs_page_exists():
    assert client.get("/docs").status_code == 200


# ---------- /chat ----------
def test_chat_returns_answer_and_sources(monkeypatch):
    seen = {}

    def fake_answer(question, ticker=None, use_cache=True):
        seen.update(question=question, ticker=ticker)
        return FAKE_CHAT

    monkeypatch.setattr(chat_route, "answer_chat", fake_answer)
    response = client.post("/chat", json={"question": "  What are NVIDIA's risks?  ", "ticker": "nvda"})
    assert response.status_code == 200
    assert response.json()["sources"][0]["ticker"] == "NVDA"
    assert seen == {"question": "What are NVIDIA's risks?", "ticker": "NVDA"}   # cleaned by the schema


@pytest.mark.parametrize("payload", [
    {"question": ""},                                  # empty
    {"question": "hi"},                                # too short
    {"question": "What is revenue?", "ticker": "TSLA"},  # unsupported company
    {"wrong_field": "x"},                              # missing question
])
def test_chat_rejects_bad_input(payload):
    assert client.post("/chat", json=payload).status_code == 422


def test_chat_llm_down_gives_503(monkeypatch):
    def broken(*args, **kwargs):
        raise LLMError("All models failed. Gemini free-tier limit reached.")
    monkeypatch.setattr(chat_route, "answer_chat", broken)
    response = client.post("/chat", json={"question": "What are Apple's risks?"})
    assert response.status_code == 503
    assert "free-tier" in response.json()["detail"]


def test_unexpected_error_hides_details(monkeypatch):
    def crash(*args, **kwargs):
        raise KeyError("secret internal detail")
    monkeypatch.setattr(chat_route, "answer_chat", crash)
    response = client.post("/chat", json={"question": "What are Apple's risks?"})
    assert response.status_code == 500
    assert "secret" not in response.text


# ---------- /uploads ----------
@pytest.mark.skipif(not SAMPLES.exists(), reason="samples/ missing")
def test_upload_list_get_delete(uploads_tmp):
    with open(SAMPLES / "kestrel_financials.csv", "rb") as f:
        response = client.post("/uploads", files={"file": ("kestrel_financials.csv", f, "text/csv")})
    assert response.status_code == 201
    doc_id = response.json()["doc_id"]
    assert response.json()["kind"] == "table"

    assert [u["doc_id"] for u in client.get("/uploads").json()] == [doc_id]
    assert client.get(f"/uploads/{doc_id}").json()["filename"] == "kestrel_financials.csv"
    assert client.delete(f"/uploads/{doc_id}").status_code == 204
    assert client.get(f"/uploads/{doc_id}").status_code == 404


def test_upload_bad_file_gives_400(uploads_tmp):
    response = client.post("/uploads", files={"file": ("tool.exe", b"MZ...", "application/octet-stream")})
    assert response.status_code == 400
    assert "not accepted" in response.json()["detail"]


def test_ask_unknown_doc_gives_404(uploads_tmp):
    response = client.post("/uploads/ask", json={"question": "Total revenue?", "doc_ids": ["abc123def456"]})
    assert response.status_code == 404


def test_ask_table_answer_with_nan_is_valid_json(monkeypatch):
    fake = {"answer": "Revenue grew 10.66% in 2025.", "documents": ["f.csv"], "used_llm": True,
            "model": "fake", "cached": False,
            "sources": [{"filename": "f.csv", "sheet": "csv", "detail": "growth of Revenue"}],
            "calculation": {"plan": {"operation": "growth"}, "summary": "growth",
                            "table": [{"Year": 2024, "change_%": float("nan")},
                                      {"Year": 2025, "change_%": 10.66}]}}
    monkeypatch.setattr(uploads_route, "answer_upload_question", lambda *a, **k: fake)
    response = client.post("/uploads/ask", json={"question": "Revenue growth?", "doc_ids": ["abc123def456"]})
    assert response.status_code == 200
    assert response.json()["calculation"]["table"][0]["change_%"] is None   # NaN -> null


def test_ask_requires_doc_ids():
    assert client.post("/uploads/ask", json={"question": "Total revenue?", "doc_ids": []}).status_code == 422
