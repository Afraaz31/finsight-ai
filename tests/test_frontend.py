"""UI tests (Level 9 redesign): every page of the multi-page Streamlit app, run headless with AppTest.

The API client is replaced by fakes: no backend, no browser, no internet, no quota.
"""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from frontend import api_client, ui
from frontend.api_client import ApiError
from frontend.logos import company_logo, finsight_mark

APP = str(Path(__file__).resolve().parents[1] / "frontend" / "app.py")
HEALTH = {"status": "ok", "sec_chunks": 4593, "uploads": 0, "llm_model": "gemini-3.5-flash-lite",
          "fallback_models": ["gemini-3.1-flash-lite"], "ollama_enabled": True,
          "api_key_configured": True, "problems": []}
COMPANIES = [{"ticker": t, "name": n, "cik": "0", "fiscal_years": [2025, 2026]} for t, n in
             [("AAPL", "Apple Inc."), ("MSFT", "Microsoft Corporation"), ("AMZN", "Amazon.com, Inc."),
              ("GOOGL", "Alphabet Inc."), ("NVDA", "NVIDIA Corporation")]]
METRICS = [{"metric": "revenue", "label": "Revenue", "period_type": "duration"},
           {"metric": "net_income", "label": "Net income", "period_type": "duration"}]


def row(ticker, metric, fy, value, yoy=None, rank=None):
    return {"ticker": ticker, "company": ticker, "metric": metric, "label": metric, "fiscal_year": fy,
            "period_start": f"{fy - 1}-01-01", "period_end": f"{fy}-12-31", "value": value,
            "value_display": f"${value / 1e9:,.2f}B", "unit": "USD", "tag": "Revenues", "derived": False,
            "form": "10-K", "accession": "x", "filed": f"{fy}-02-01", "source_url": "https://www.sec.gov/x/",
            "yoy_change_pct": yoy, "rank": rank, "share_of_leader_pct": 100.0 if rank == 1 else 62.65}


def fake_financials(ticker):
    return {"ticker": ticker, "company": ticker, "metrics": [
        {"metric": "revenue", "label": "Revenue", "latest": None,
         "history": [row(ticker, "revenue", 2025, 400e9), row(ticker, "revenue", 2026, 440e9, 10.0)]},
        {"metric": "net_income", "label": "Net income", "latest": None,
         "history": [row(ticker, "net_income", 2025, 100e9), row(ticker, "net_income", 2026, 120e9, 20.0)]},
        {"metric": "gross_profit", "label": "Gross profit", "latest": None, "history": []}]}


COMPARISON = {"metric": "revenue", "label": "Revenue", "fiscal_year": None,
              "summary": "Apple Inc.'s revenue ($478.83B, FY2026) is $147.00B higher than Microsoft's.",
              "notes": ["Fiscal years end on different dates (AAPL 2026-09-26, MSFT 2026-06-30)."],
              "rows": [row("AAPL", "revenue", 2026, 478.83e9, rank=1), row("MSFT", "revenue", 2026, 331.84e9, rank=2)]}
SEC_ANSWER = {"answer": "Apple's revenue was $478.83B, $147.00B more than Microsoft's [F].", "sources": [],
              "companies": ["AAPL", "MSFT"], "used_llm": True, "model": "gemini-3.5-flash-lite", "cached": False,
              "retrieved_chunks": 0, "unverified_numbers": [], "route": "numbers", "financials": [COMPARISON]}


@pytest.fixture(autouse=True)
def fake_api(monkeypatch):
    st.cache_data.clear()                 # cached API data must not leak between tests
    monkeypatch.setattr(api_client, "health", lambda: HEALTH)
    monkeypatch.setattr(api_client, "companies", lambda: COMPANIES)
    monkeypatch.setattr(api_client, "metrics", lambda: METRICS)
    monkeypatch.setattr(api_client, "financials", fake_financials)
    monkeypatch.setattr(api_client, "list_uploads", lambda: [])
    monkeypatch.setattr(api_client, "compare", lambda tickers, metric, fy: COMPARISON)


def open_page(page: str | None = None) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    if page:
        app.switch_page(page).run()
    assert not app.exception, app.exception
    return app


def all_markdown(app: AppTest) -> str:
    return " ".join(m.value for m in app.markdown)


# ---------------- pages ----------------
def test_home_shows_brand_and_five_company_cards():
    app = open_page()
    text = all_markdown(app)
    assert "FinSight AI" in text
    for name in ["Apple Inc.", "Microsoft Corporation", "Amazon.com, Inc.", "Alphabet Inc.", "NVIDIA Corporation"]:
        assert name in text
    assert "$440.00B" in text                                    # latest revenue on the cards
    assert any(b.label == "📂  Upload files" for b in app.button)


def test_api_down_shows_clear_error(monkeypatch):
    def down():
        raise ApiError(0, "Can't reach the FinSight API")
    monkeypatch.setattr(api_client, "health", down)
    app = AppTest.from_file(APP, default_timeout=30)
    app.run()
    assert any("not running" in e.value for e in app.error)


def test_ask_page_numbers_answer_shows_table_and_trail(monkeypatch):
    seen = {}

    def fake_chat(question, ticker, use_cache):
        seen.update(question=question, ticker=ticker)
        return SEC_ANSWER
    monkeypatch.setattr(api_client, "chat", fake_chat)
    app = open_page("views/ask.py")
    assert any("Compare Apple's revenue with Microsoft's" == b.label for b in app.button)   # full-text suggestions
    app.chat_input[0].set_value("Compare Apple's revenue with Microsoft's").run()
    assert not app.exception
    assert seen["question"] == "Compare Apple's revenue with Microsoft's"
    assert len(app.dataframe) == 1                                # exact figures table
    assert any("How this answer was made" in e.label for e in app.expander)
    assert "\\$478.83B" in all_markdown(app)                     # $ escaped, so no LaTeX


def test_ask_page_shows_api_errors(monkeypatch):
    def failing(*args):
        raise ApiError(503, "Gemini free-tier limit reached.")
    monkeypatch.setattr(api_client, "chat", failing)
    app = open_page("views/ask.py")
    app.chat_input[0].set_value("What are Apple's risks?").run()
    assert not app.exception
    assert any("free-tier" in e.value for e in app.error)


def test_upload_page_has_dropzone_and_samples():
    app = open_page("views/upload.py")
    labels = [b.label for b in app.button]
    assert "📄 Annual report (PDF)" in labels and "📗 Statements (XLSX)" in labels
    assert any("Select at least one file" in i.value for i in app.info)


def test_upload_page_table_answer_shows_python_calculation(monkeypatch):
    upload = {"doc_id": "abc123def456", "filename": "f.csv", "extension": ".csv", "kind": "table",
              "uploaded_at": "x", "size_bytes": 2048,
              "tables": [{"sheet": "csv", "file": "table_0.csv", "rows": 4, "columns": ["Year"],
                          "reshaped_to_long": False}]}
    result = {"answer": "Margin was 14.03% in 2025.", "documents": ["f.csv"], "used_llm": True, "model": "fake",
              "cached": True, "unverified_numbers": [],
              "sources": [{"filename": "f.csv", "sheet": "csv", "detail": "ratio per Year"}],
              "calculation": {"plan": {"operation": "ratio"}, "summary": "ratio per Year",
                              "table": [{"Year": 2024, "ratio_%": None}, {"Year": 2025, "ratio_%": 14.03}]}}
    monkeypatch.setattr(api_client, "list_uploads", lambda: [upload])
    monkeypatch.setattr(api_client, "ask_uploads", lambda *a: result)
    app = open_page("views/upload.py")
    app.checkbox[0].check().run()
    app.chat_input[0].set_value("What is the margin?").run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert "done by Python" in all_markdown(app)


def test_compare_page_ranking_and_notes():
    app = open_page("views/compare.py")
    assert len(app.dataframe) >= 1
    assert any("$147.00B higher" in s.value for s in app.success)
    assert any("different dates" in c.value for c in app.caption)


def test_dashboard_shows_kpis_and_python_insights():
    app = open_page("views/dashboard.py")
    text = all_markdown(app)
    assert "$440.00B" in text and "Net profit margin" in text
    assert "27.3%" in text                                        # 120 / 440, calculated by Python
    assert "not reported" in text                                 # gross profit missing -> said honestly


def test_dashboard_switches_company_on_every_click():
    """Regression: with a changing default= the company picker dropped every second click."""
    app = open_page("views/dashboard.py")
    for ticker in ["MSFT", "AMZN", "NVDA", "GOOGL"]:
        app.button_group[0].set_value(ticker).run()
        assert not app.exception
        assert any(f"({ticker})" in m.value for m in app.markdown if "fs-brand" in m.value), ticker


def test_how_it_works_page():
    app = open_page("views/how_it_works.py")
    assert "Pipeline A" in all_markdown(app) and "Number guard" in all_markdown(app)


# ---------------- helpers ----------------
def test_logos_and_helpers():
    for ticker in ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"]:
        assert company_logo(ticker).startswith("<svg")
    assert "<svg" in finsight_mark(40)
    assert ui.safe_md("$5 and $6") == "\\$5 and \\$6"
    assert ui.fmt_money(478.834e9) == "$478.83B"
