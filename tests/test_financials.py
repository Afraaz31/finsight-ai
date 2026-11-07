"""Level 7 tests: SEC Company Facts extraction, comparisons, question routing, hybrid chat, API.

Uses a small FAKE Company Facts structure that contains the real-world traps:
comparative prior-year values, quarterly numbers inside a 10-K, a 10-K/A amendment, a 10-Q,
a tag that changed over the years, and a company that doesn't report total liabilities.
No internet, no API key, no quota.
"""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import chat_service, financial_service
from backend.services.financial_service import (UnknownCompany, annual_facts, compare,
                                                extract_metrics, format_money)
from backend.services.llm_service import LLMError
from backend.services.question_router import detect_metrics, route

B = 1_000_000_000


def fact(start, end, val, accn, filed, form="10-K", fp="FY"):
    f = {"end": end, "val": val, "accn": accn, "filed": filed, "form": form, "fp": fp}
    if start:
        f["start"] = start
    return f


def facts_json(tags: dict) -> dict:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}}}


APPLE_LIKE = facts_json({
    "RevenueFromContractWithCustomerExcludingAssessedTax": [
        fact("2025-09-28", "2026-09-26", 478.834 * B, "A-26", "2026-11-03"),         # FY2026 (current)
        fact("2024-09-29", "2025-09-27", 416.161 * B, "A-26", "2026-11-03"),         # comparative -> ignore
        fact("2026-06-28", "2026-09-26", 120.0 * B, "A-26", "2026-11-03"),           # quarter -> ignore
        fact("2024-09-29", "2025-09-27", 416.161 * B, "A-25", "2025-10-31"),         # FY2025 (original)
        fact("2023-10-01", "2024-09-28", 391.035 * B, "A-25", "2025-10-31"),         # comparative
        fact("2024-09-29", "2025-09-27", 999.0 * B, "A-25A", "2026-01-15", form="10-K/A"),  # amendment
        fact("2026-06-28", "2026-09-26", 50.0 * B, "Q-26", "2026-08-01", form="10-Q", fp="Q3"),
    ],
    "SalesRevenueNet": [fact("2017-10-01", "2018-09-29", 265.595 * B, "A-18", "2018-11-05")],  # old tag
    "NetIncomeLoss": [fact("2025-09-28", "2026-09-26", 120.0 * B, "A-26", "2026-11-03")],
    "GrossProfit": [fact("2025-09-28", "2026-09-26", 220.0 * B, "A-26", "2026-11-03")],
    "Assets": [
        fact(None, "2026-09-26", 380.0 * B, "A-26", "2026-11-03"),
        fact(None, "2025-09-27", 365.0 * B, "A-26", "2026-11-03"),     # comparative in the FY2026 10-K
        fact(None, "2025-09-27", 364.0 * B, "A-25", "2025-10-31"),     # original FY2025 value
    ],
    "Liabilities": [fact(None, "2026-09-26", 300.0 * B, "A-26", "2026-11-03")],
})

MSFT_LIKE = facts_json({
    "RevenueFromContractWithCustomerExcludingAssessedTax": [
        fact("2025-07-01", "2026-06-30", 300.0 * B, "M-26", "2026-07-30")],
    "NetIncomeLoss": [fact("2025-07-01", "2026-06-30", 110.0 * B, "M-26", "2026-07-30")],
    # no GrossProfit tag here on purpose
    "LiabilitiesAndStockholdersEquity": [fact(None, "2026-06-30", 600.0 * B, "M-26", "2026-07-30")],
    "StockholdersEquity": [fact(None, "2026-06-30", 350.0 * B, "M-26", "2026-07-30")],
})


@pytest.fixture
def metrics_csv(tmp_path, monkeypatch):
    rows = extract_metrics(APPLE_LIKE, "AAPL") + extract_metrics(MSFT_LIKE, "MSFT")
    path = tmp_path / "metrics.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    monkeypatch.setattr(financial_service, "METRICS_PATH", path)
    monkeypatch.setattr(chat_service, "METRICS_PATH", path)
    financial_service._cache.update(mtime=None, df=None)
    return path


# ---------- extraction ----------
def test_annual_facts_keep_only_each_filings_own_year():
    facts = annual_facts(APPLE_LIKE, "RevenueFromContractWithCustomerExcludingAssessedTax", "duration")
    # FY2024 appears only as a comparison column inside the FY2025 10-K -> not used.
    # (In real SEC data every year also has its own 10-K, so no year is lost.)
    assert [(f["end"], f["accn"]) for f in facts] == [("2025-09-27", "A-25"), ("2026-09-26", "A-26")]
    assert all(f["form"] == "10-K" for f in facts)                 # no 10-K/A, no 10-Q
    assert facts[-1]["val"] == 478.834 * B                          # not the 120B quarter


def test_best_tag_per_year_includes_old_tag_years():
    revenue = [r for r in extract_metrics(APPLE_LIKE, "AAPL") if r["metric"] == "revenue"]
    assert [r["fiscal_year"] for r in revenue] == [2018, 2025, 2026]
    assert revenue[0]["tag"] == "SalesRevenueNet"
    assert revenue[-1]["source_url"] == "https://www.sec.gov/Archives/edgar/data/320193/A26/"


def test_balance_sheet_uses_original_filing():
    assets = [r for r in extract_metrics(APPLE_LIKE, "AAPL") if r["metric"] == "total_assets"]
    fy2025 = next(r for r in assets if r["fiscal_year"] == 2025)
    assert fy2025["value"] == 364.0 * B and fy2025["accession"] == "A-25"


def test_missing_liabilities_are_derived_and_flagged():
    liab = [r for r in extract_metrics(MSFT_LIKE, "MSFT") if r["metric"] == "total_liabilities"]
    assert liab[0]["value"] == 250.0 * B and liab[0]["derived"] is True


def test_metric_tagged_only_long_ago_counts_as_not_reported():
    # Real trap found in SEC data: Amazon tagged GrossProfit only in its FY2009 10-K.
    amzn_like = facts_json({
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            fact("2025-01-01", "2025-12-31", 716.924 * B, "Z-25", "2026-02-06")],
        "GrossProfit": [fact("2009-01-01", "2009-12-31", 5.531 * B, "Z-09", "2010-01-29")],
    })
    assert {r["metric"] for r in extract_metrics(amzn_like, "AMZN")} == {"revenue"}


def test_format_money():
    assert format_money(478.834 * B) == "$478.83B"
    assert format_money(-2.3 * B) == "-$2.30B"
    assert format_money(850_000_000) == "$850.0M"


# ---------- comparisons ----------
def test_compare_two_companies(metrics_csv):
    result = compare(["AAPL", "MSFT"], "revenue")
    assert [r["ticker"] for r in result["rows"]] == ["AAPL", "MSFT"]
    assert "$178.83B higher" in result["summary"]
    assert "59.61% higher" in result["summary"]                     # 478.834 / 300 - 1, by Python
    assert any("different dates" in n for n in result["notes"])     # Sep vs Jun year ends


def test_compare_reports_missing_metric(metrics_csv):
    result = compare(["AAPL", "MSFT"], "gross_profit")
    assert [r["ticker"] for r in result["rows"]] == ["AAPL"]
    assert any("Microsoft Corporation does not report gross profit" in n for n in result["notes"])


def test_compare_unknown_company_and_metric(metrics_csv):
    with pytest.raises(UnknownCompany):
        compare(["AAPL", "TSLA"], "revenue")
    with pytest.raises(ValueError):
        compare(["AAPL", "MSFT"], "ebitda")


def test_history_has_year_over_year_change(metrics_csv):
    rows = financial_service.history("AAPL", "revenue")
    assert rows[-1]["yoy_change_pct"] == pytest.approx(15.06, abs=0.01)


# ---------- routing ----------
@pytest.mark.parametrize("question, expected_route, metrics", [
    ("What was Apple's revenue in its latest fiscal year?", "numbers", ["revenue"]),
    ("Compare Apple's revenue with Microsoft's", "numbers", ["revenue"]),
    ("Which company reported the highest net income?", "numbers", ["net_income"]),
    ("Explain Amazon's operating income", "both", ["operating_income"]),
    ("Compare the financial performance of all five companies", "numbers",
     ["revenue", "operating_income", "net_income"]),
    ("What are Microsoft's major business risks?", "narrative", []),
    ("Summarize NVIDIA's annual report", "narrative", []),
    ("What is Apple's operating cash flow?", "numbers", ["operating_cash_flow"]),
])
def test_router(question, expected_route, metrics):
    assert route(question) == {"route": expected_route, "metrics": metrics}


def test_gross_profit_is_not_also_net_income():
    assert detect_metrics("What is NVIDIA's gross profit?") == ["gross_profit"]


# ---------- hybrid chat ----------
def test_numbers_question_uses_python_figures(metrics_csv, monkeypatch):
    seen = {}

    def fake_llm(system, user):
        seen["user"] = user
        return "Apple's revenue was $478.83B (FY2026), $178.83B higher than Microsoft's [F].", "fake-model"

    monkeypatch.setattr(chat_service, "generate_answer", fake_llm)
    result = chat_service.answer_chat("Compare Apple's revenue with Microsoft's")
    assert result["route"] == "numbers"
    assert "$478.83B" in seen["user"] and "59.61% higher" in seen["user"]
    assert result["financials"][0]["rows"][0]["ticker"] == "AAPL"
    assert result["unverified_numbers"] == []


def test_numbers_question_still_answers_when_llm_is_down(metrics_csv, monkeypatch):
    def down(*args):
        raise LLMError("All models failed")
    monkeypatch.setattr(chat_service, "generate_answer", down)
    result = chat_service.answer_chat("Compare Apple's revenue with Microsoft's")
    assert result["used_llm"] is False
    assert "$478.83B" in result["answer"]                            # exact figures, written by Python


def test_narrative_question_goes_to_rag(monkeypatch):
    monkeypatch.setattr(chat_service, "answer_question",
                        lambda q, ticker=None, use_cache=True: {"answer": "risks [1]", "sources": []})
    result = chat_service.answer_chat("What are Microsoft's major business risks?")
    assert result["route"] == "narrative" and result["financials"] is None


# ---------- API ----------
client = TestClient(app, raise_server_exceptions=False)


def test_api_metrics_and_financials(metrics_csv):
    assert "revenue" in [m["metric"] for m in client.get("/metrics").json()]
    body = client.get("/financials/aapl").json()
    revenue = next(m for m in body["metrics"] if m["metric"] == "revenue")
    assert revenue["latest"]["value_display"] == "$478.83B"
    assert client.get("/financials/TSLA").status_code == 404


def test_api_compare(metrics_csv):
    response = client.post("/compare", json={"tickers": ["aapl", "msft"], "metric": "revenue"})
    assert response.status_code == 200
    assert response.json()["rows"][1]["share_of_leader_pct"] == pytest.approx(62.65, abs=0.01)
    assert client.post("/compare", json={"tickers": ["AAPL", "MSFT"], "metric": "ebitda"}).status_code == 422
    assert client.post("/compare", json={"tickers": ["AAPL"], "metric": "revenue"}).status_code == 422


def test_api_without_financial_data_gives_503(tmp_path, monkeypatch):
    monkeypatch.setattr(financial_service, "METRICS_PATH", tmp_path / "missing.csv")
    financial_service._cache.update(mtime=None, df=None)
    response = client.post("/compare", json={"tickers": ["AAPL", "MSFT"], "metric": "revenue"})
    assert response.status_code == 503
    assert "fetch_financial_facts" in response.json()["detail"]
