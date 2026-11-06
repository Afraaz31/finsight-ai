"""Level 3 tests: question understanding, prompt building and the pipeline.

Gemini and the vector store are replaced by fakes, so these tests need no internet,
no API key and use no quota.
"""
import pytest

from backend.services import rag_service
from backend.services.llm_service import friendly_message
from backend.services.rag_service import (answer_question, build_context, detect_companies,
                                          detect_sections)


def fake_hit(chunk_id: str, ticker: str, score: float = 0.6) -> dict:
    return {
        "id": chunk_id,
        "score": score,
        "text": f"{ticker} Inc. | FY2026 Form 10-K | Item 1A. Risk Factors\nSupply chain risk text for {ticker}.",
        "metadata": {"company": f"{ticker} Inc.", "ticker": ticker, "fiscal_year": 2026,
                     "report_date": "2026-09-26", "section": "Item 1A. Risk Factors",
                     "document_url": f"https://www.sec.gov/{ticker}.htm"},
    }


# ---------- question understanding ----------
def test_detect_companies_by_name_and_ticker():
    assert detect_companies("Compare Apple's revenue with MSFT") == ["AAPL", "MSFT"]
    assert detect_companies("How is Google doing?") == ["GOOGL"]
    assert detect_companies("Compare all five companies") == ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"]
    assert detect_companies("What are the laws on tax?") == []   # "aws" inside "laws" must not match


def test_detect_sections():
    assert detect_sections("What are NVIDIA's major business risks?") == ["1A"]
    assert detect_sections("What is Apple's interest rate exposure?") == ["7A"]   # before "risk"
    assert detect_sections("Explain the business segments of Alphabet") == ["1"]
    assert detect_sections("Summarize Amazon's annual report") == ["1", "7", "1A"]
    assert detect_sections("Tell me about Apple") == [None]


# ---------- prompt building ----------
def test_build_context_numbers_sources_with_period():
    context = build_context([fake_hit("a", "AAPL"), fake_hit("b", "MSFT")])
    assert context.startswith("[1] AAPL Inc. | Form 10-K FY2026 (period ending 2026-09-26)")
    assert "\n\n[2] MSFT Inc." in context
    assert "Supply chain risk text for MSFT." in context


# ---------- pipeline (with fakes) ----------
def test_no_evidence_means_no_gemini_call(monkeypatch):
    monkeypatch.setattr(rag_service, "search", lambda *a, **k: [fake_hit("weak", "AAPL", score=0.05)])
    monkeypatch.setattr(rag_service, "generate",
                        lambda *a, **k: pytest.fail("Gemini must not be called without evidence"))
    result = answer_question("What is Apple's favourite colour?")
    assert result["used_llm"] is False
    assert result["sources"] == []


def test_each_company_gets_its_own_search(monkeypatch):
    searched = []

    def fake_search(question, k, ticker=None, **kwargs):
        searched.append(ticker)
        return [fake_hit(f"{ticker}-1", ticker)]

    monkeypatch.setattr(rag_service, "search", fake_search)
    monkeypatch.setattr(rag_service, "generate", lambda system, user: "Apple has risks [1]; Microsoft too [2].")
    result = answer_question("Compare Apple and Microsoft risks")
    assert searched == ["AAPL", "MSFT"]
    assert [s["ticker"] for s in result["sources"]] == ["AAPL", "MSFT"]
    assert all(s["cited"] for s in result["sources"])
    assert result["sources"][0]["document_url"] == "https://www.sec.gov/AAPL.htm"


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        answer_question("   ")


# ---------- error messages ----------
def test_friendly_messages():
    assert "free-tier limit" in friendly_message(429)
    assert "not found" in friendly_message(404)
    assert "GEMINI_API_KEY" in friendly_message(403)
    assert "temporarily unavailable" in friendly_message(503)


def test_missing_api_key_gives_clear_error(monkeypatch):
    from backend.services import llm_service
    monkeypatch.setattr(llm_service, "_client", None)
    monkeypatch.setattr(llm_service, "GEMINI_API_KEY", "your_gemini_api_key_here")
    with pytest.raises(llm_service.LLMError, match="GEMINI_API_KEY is not set"):
        llm_service.generate("system", "question")
