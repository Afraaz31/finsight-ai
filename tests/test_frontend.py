"""Level 6 tests: the Streamlit UI, run headless with Streamlit's AppTest (no browser, no server).

The API client functions are replaced by fakes, so no backend, no internet and no quota are needed.
"""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend import api_client
from frontend.api_client import ApiError

APP = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")   # absolute path
HEALTH = {"status": "ok", "sec_chunks": 4593, "uploads": 0, "llm_model": "gemini-3.5-flash-lite",
          "fallback_models": ["gemini-3.1-flash-lite"], "ollama_enabled": True,
          "api_key_configured": True, "problems": []}
COMPANIES = [{"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193", "fiscal_years": [2025, 2026]}]
ANSWER = {"answer": "Apple faces supply chain risk [1].", "companies": ["AAPL"], "used_llm": True,
          "model": "gemini-3.5-flash-lite", "cached": False, "retrieved_chunks": 5, "unverified_numbers": [],
          "sources": [{"number": 1, "company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026,
                       "period_end": "2026-09-26", "section": "Item 1A. Risk Factors",
                       "document_url": "https://www.sec.gov/x.htm", "score": 0.6, "excerpt": "Supply..."}]}


@pytest.fixture(autouse=True)
def fake_api(monkeypatch):
    st.cache_data.clear()          # cached health/companies must not leak between tests
    monkeypatch.setattr(api_client, "health", lambda: HEALTH)
    monkeypatch.setattr(api_client, "companies", lambda: COMPANIES)
    monkeypatch.setattr(api_client, "list_uploads", lambda: [])


def run_app() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert not app.exception, app.exception
    return app


def test_app_loads_with_title_and_suggestions():
    app = run_app()
    assert app.title[0].value == "FinSight AI"
    assert any("NVIDIA" in b.label for b in app.button)          # suggested questions
    assert "4,593 SEC chunks" in app.sidebar.success[0].value


def test_api_down_shows_clear_error(monkeypatch):
    def down():
        raise ApiError(0, "Can't reach the FinSight API")
    monkeypatch.setattr(api_client, "health", down)
    app = run_app()
    assert any("not running" in e.value for e in app.error)


def test_question_shows_answer_and_sources(monkeypatch):
    seen = {}

    def fake_chat(question, ticker, use_cache):
        seen.update(question=question, ticker=ticker)
        return ANSWER
    monkeypatch.setattr(api_client, "chat", fake_chat)
    app = run_app()
    app.chat_input[0].set_value("What are Apple's risks?").run()
    assert not app.exception
    assert seen["question"] == "What are Apple's risks?"
    assert any("supply chain risk" in m.value for m in app.markdown)
    assert any("Item 1A" in e.label for e in app.expander)       # a source expander


def test_api_error_is_shown_not_crashed(monkeypatch):
    def failing_chat(*args):
        raise ApiError(503, "Gemini free-tier limit reached.")
    monkeypatch.setattr(api_client, "chat", failing_chat)
    app = run_app()
    app.chat_input[0].set_value("What are Apple's risks?").run()
    assert not app.exception
    assert any("free-tier" in e.value for e in app.error)


def test_upload_mode_without_files_shows_hint():
    app = run_app()
    app.sidebar.radio[0].set_value("My uploaded files").run()
    assert not app.exception
    assert any("No files yet" in i.value for i in app.sidebar.info)


def test_table_answer_shows_python_calculation(monkeypatch):
    upload = {"doc_id": "abc123def456", "filename": "f.csv", "kind": "table", "uploaded_at": "x",
              "tables": [{"sheet": "csv", "file": "table_0.csv", "rows": 4, "columns": ["Year"],
                          "reshaped_to_long": False}]}
    result = {"answer": "Margin was 14.03% in 2025.", "documents": ["f.csv"], "used_llm": True,
              "model": "fake", "cached": True, "unverified_numbers": [],
              "sources": [{"filename": "f.csv", "sheet": "csv", "detail": "ratio per Year"}],
              "calculation": {"plan": {"operation": "ratio"}, "summary": "ratio per Year",
                              "table": [{"Year": 2025, "ratio_%": 14.03}]}}
    monkeypatch.setattr(api_client, "list_uploads", lambda: [upload])
    monkeypatch.setattr(api_client, "ask_uploads", lambda *a: result)
    app = run_app()
    app.sidebar.radio[0].set_value("My uploaded files").run()
    app.sidebar.checkbox[0].check().run()
    app.chat_input[0].set_value("What is the margin?").run()
    assert not app.exception
    assert len(app.dataframe) == 1                                # the calculation table
    assert any("done by Python" in m.value for m in app.markdown)


# ---------- Level 7 ----------
COMPARISON = {"metric": "revenue", "label": "Revenue", "fiscal_year": None,
              "summary": "Apple Inc.'s revenue ($478.83B, FY2026) is $178.83B higher than Microsoft's.",
              "notes": ["Fiscal years end on different dates (AAPL 2026-09-26, MSFT 2026-06-30)."],
              "rows": [{"ticker": "AAPL", "company": "Apple Inc.", "fiscal_year": 2026, "period_end": "2026-09-26",
                        "value": 478.834e9, "value_display": "$478.83B", "derived": False, "rank": 1,
                        "share_of_leader_pct": 100.0, "source_url": "https://www.sec.gov/a/"},
                       {"ticker": "MSFT", "company": "Microsoft Corporation", "fiscal_year": 2026,
                        "period_end": "2026-06-30", "value": 300e9, "value_display": "$300.00B", "derived": False,
                        "rank": 2, "share_of_leader_pct": 62.65, "source_url": "https://www.sec.gov/m/"}]}


def test_numbers_answer_shows_exact_figures_table(monkeypatch):
    answer = {**ANSWER, "sources": [], "route": "numbers", "financials": [COMPARISON],
              "answer": "Apple's revenue was $478.83B [F]."}
    monkeypatch.setattr(api_client, "chat", lambda *a: answer)
    app = run_app()
    app.chat_input[0].set_value("Compare Apple's revenue with Microsoft's").run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert any("$178.83B higher" in s.value for s in app.success)


def test_compare_mode_shows_table_and_summary(monkeypatch):
    monkeypatch.setattr(api_client, "metrics", lambda: [{"metric": "revenue", "label": "Revenue",
                                                         "period_type": "duration"}])
    monkeypatch.setattr(api_client, "companies", lambda: COMPANIES + [
        {"ticker": "MSFT", "name": "Microsoft Corporation", "cik": "0000789019", "fiscal_years": [2025, 2026]}])
    seen = {}

    def fake_compare(tickers, metric, fiscal_year):
        seen.update(tickers=tickers, metric=metric, fiscal_year=fiscal_year)
        return COMPARISON
    monkeypatch.setattr(api_client, "compare", fake_compare)
    app = run_app()
    app.sidebar.radio[0].set_value("Compare financials (exact SEC figures)").run()
    next(b for b in app.button if b.label == "Compare").click().run()
    assert not app.exception
    assert seen == {"tickers": ["AAPL", "MSFT"], "metric": "revenue", "fiscal_year": None}
    assert len(app.dataframe) == 1
    assert any("different dates" in c.value for c in app.caption)


def test_dollar_amounts_are_not_rendered_as_math(monkeypatch):
    # Streamlit renders text between two "$" signs as LaTeX; the UI must escape them.
    answer = {**ANSWER, "answer": "Apple's revenue was $478.83B and Microsoft's was $331.84B [1]."}
    monkeypatch.setattr(api_client, "chat", lambda *a: answer)
    app = run_app()
    app.chat_input[0].set_value("Compare Apple's revenue with Microsoft's").run()
    assert not app.exception
    assert any("\$478.83B" in m.value and "\$331.84B" in m.value for m in app.markdown)
