"""Level 8 tests: the demo questions route the way the demo plan expects (no quota used)."""
import pytest

from backend.services import chat_service
from backend.services.question_router import route
from scripts.prewarm import DEMO_QUESTIONS

EXPECTED = {
    "What are NVIDIA's major business risks?": "narrative",
    "What was Apple's revenue in its latest reported fiscal year?": "numbers",
    "Compare Apple's revenue with Microsoft's": "numbers",
    "Which company reported the highest net income?": "numbers",
    "Compare the financial performance of all five companies": "numbers",
    "Explain Amazon's operating income": "both",
    "Explain the business segments of Alphabet": "narrative",
    "Summarize the management discussion in Apple's annual report": "narrative",
    "What are Microsoft's major business risks?": "narrative",
    "What is Tesla's revenue?": "numbers",   # the router sees "revenue"; chat_service then sends it to RAG
    "Audit report of Apple": "report",
    "Audit report of Microsoft": "report",
    "Audit report of Amazon": "report",
    "Audit report of Alphabet": "report",
    "Audit report of NVIDIA": "report",
    "Was Apple's 2026 profit better than 2025?": "both",   # figures (year over year) + the 10-K explanation
}


def test_every_demo_question_has_an_expected_route():
    assert set(DEMO_QUESTIONS) == set(EXPECTED)


@pytest.mark.parametrize("question", DEMO_QUESTIONS)
def test_demo_question_routes(question):
    assert route(question)["route"] == EXPECTED[question]


def test_unsupported_company_number_question_goes_to_rag(monkeypatch):
    """Regression: 'What is Tesla's revenue?' must NOT compare the 5 supported companies."""
    monkeypatch.setattr(chat_service, "answer_question",
                        lambda q, ticker=None, use_cache=True: {"answer": "Tesla is not covered.", "sources": []})
    monkeypatch.setattr(chat_service, "compare",
                        lambda *a, **k: pytest.fail("must not compare companies for a Tesla question"))
    result = chat_service.answer_chat("What is Tesla's revenue?")
    assert result["route"] == "narrative" and result["financials"] is None


def test_ranking_question_without_company_uses_all_five():
    assert chat_service._companies_for("Which company reported the highest net income?", None) == [
        "AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"]
