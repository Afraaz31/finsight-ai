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


# ---------- Level 10: exact sources ----------
PASSAGE = ("In our opinion, the consolidated financial statements present fairly, in all material respects, "
           "the financial position of Apple Inc. The firm Ernst & Young LLP has served as auditor since 2009.")
AUDIT_ANSWER = {"answer": "Apple's auditor, Ernst & Young LLP, issued an unqualified opinion [1].",
                "sources": [{"number": 1, "company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026,
                             "period_end": "2026-09-26", "section": "Item 8. Financial Statements",
                             "document_url": "https://www.sec.gov/x.htm", "score": 0.71, "excerpt": PASSAGE[:300],
                             "text": PASSAGE, "section_id": "8",
                             "deep_link": "https://www.sec.gov/x.htm#:~:text=In%20our%20opinion,auditor"}],
                "companies": ["AAPL"], "used_llm": True, "model": "gemini-3.5-flash-lite", "cached": False,
                "retrieved_chunks": 4, "unverified_numbers": [], "route": "narrative", "financials": []}


def test_sources_show_full_passage_exact_link_and_full_section(monkeypatch):
    monkeypatch.setattr(api_client, "chat", lambda q, t, c: AUDIT_ANSWER)
    calls = []

    def fake_section(ticker, fiscal_year, section_id):
        calls.append((ticker, fiscal_year, section_id))
        return {"ticker": ticker, "company": "Apple Inc.", "fiscal_year": fiscal_year, "period_end": "2026-09-26",
                "section_id": section_id, "section": "Item 8. Financial Statements",
                "text": "Report of Independent Registered Public Accounting Firm\nIn our opinion ...",
                "char_count": 70, "document_url": "https://www.sec.gov/x.htm"}
    monkeypatch.setattr(api_client, "section", fake_section)
    app = open_page("views/ask.py")
    app.chat_input[0].set_value("Find the audit report of Apple").run()
    assert not app.exception
    text = all_markdown(app)
    assert "has served as auditor since 2009" in text                  # the full passage, not just 300 chars
    links = [b.proto.url for b in app.get("link_button")]
    assert "https://www.sec.gov/x.htm#:~:text=In%20our%20opinion,auditor" in links
    [read] = [b for b in app.button if b.label == "📖 Read the full section"]
    read.click().run()
    assert not app.exception
    assert calls == [("AAPL", 2026, "8")]
    assert "Report of Independent Registered Public Accounting Firm" in all_markdown(app)


def test_trend_answer_shows_year_over_year_table(monkeypatch):
    trend = {"metric": "net_income", "label": "Net income", "fiscal_year": None, "mode": "trend", "notes": [],
             "summary": "Apple Inc.'s net income rose from $100.00B (FY2025) to $120.00B (FY2026): "
                        "a change of +$20.00B (+20.00%).",
             "rows": [row("AAPL", "net_income", 2025, 100e9), {**row("AAPL", "net_income", 2026, 120e9, 20.0),
                                                                 "yoy_change": 20e9}]}
    answer = {**SEC_ANSWER, "answer": "Apple's net income rose 20.00% [F].", "route": "both", "financials": [trend]}
    monkeypatch.setattr(api_client, "chat", lambda q, t, c: answer)
    app = open_page("views/ask.py")
    app.chat_input[0].set_value("Was Apple's 2026 profit better than 2025?").run()
    assert not app.exception
    table = app.dataframe[0].value
    assert list(table["Fiscal year"]) == ["FY2025", "FY2026"]
    assert list(table["Change %"]) == ["—", "+20.00%"]


def test_find_in_section_shows_matches_with_surrounding_lines():
    """Searching the full section shows each match in context (signature, date, 'auditor since'), not a bare line."""
    text = "\n".join(["Statements of operations", "Net sales | $1 | $2", "Critical audit matter text.",
                      "/s/ Ernst & Young LLP", "We have served as the Company's auditor since 2009.",
                      "San Jose, California", "November 3, 2026", "Unrelated note 1", "Unrelated note 2"])
    count, shown = ui.find_in_section(text, "ernst & young")
    assert count == 1
    assert "**Ernst & Young**" in shown                                   # the match, highlighted
    assert "auditor since 2009" in shown and "November 3, 2026" in shown  # the lines around it
    assert "Unrelated note 2" not in shown and "Net sales" in shown       # 2 before, 3 after - not the whole text
    assert ui.find_in_section(text, "Deloitte") == (0, "No matches.")
    assert ui.find_in_section(text, "$1")[1].count("**\\$1**") == 1       # $ stays escaped (no LaTeX)


# ---------- Level 11: company report ----------
REPORT = {"ticker": "AAPL", "company": "Apple Inc.", "fiscal_year": 2026, "period_end": "2026-09-26",
          "sections": [{"id": "ratios", "title": "6. Financial Ratios", "table": None, "text": None, "note": None,
                        "facts": [{"label": "Net profit margin", "value": "25.00%", "note": "net income ÷ revenue",
                                   "link": None}]},
                       {"id": "risks", "title": "8. Risk Analysis", "table": None, "note": "checks",
                        "text": "- Intense competition [1].", "facts": []}],
          "skipped": ["9. Future Outlook"], "sources": [], "model": "fake", "used_llm": True, "cached": False,
          "unverified_numbers": [], "markdown": "# Apple Inc. (AAPL): Company Report"}


def test_company_report_renders_sections_and_skips(monkeypatch):
    answer = {**SEC_ANSWER, "answer": "Here is the company report for **Apple Inc.**", "route": "report",
              "financials": None, "sources": [], "report": REPORT}
    monkeypatch.setattr(api_client, "chat", lambda q, t, c: answer)
    app = open_page("views/ask.py")
    app.chat_input[0].set_value("Audit report of Apple").run()
    assert not app.exception
    text = all_markdown(app)
    assert "6. Financial Ratios" in text and "25.00%" in text and "Intense competition" in text
    assert "9. Future Outlook" in " ".join(c.value for c in app.caption)
