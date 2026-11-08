"""Level 11: the 10-section Company Report. Fake SEC data, fake search, fake Gemini: no quota, no internet."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import chat_service, financial_service, rag_service, report_service
from backend.services.financial_service import extract_metrics
from backend.services.llm_service import LLMError
from backend.services.question_router import route, wants_report
from tests.test_financials import B, fact, facts_json

client = TestClient(app)
URL = "https://www.sec.gov/Archives/edgar/data/320193/x/aapl-20260926.htm"

APPLE = facts_json({
    "RevenueFromContractWithCustomerExcludingAssessedTax": [
        fact("2025-09-28", "2026-09-26", 400 * B, "A-26", "2026-11-03"),
        fact("2024-09-29", "2025-09-27", 500 * B, "A-25", "2025-10-31")],          # revenue FELL
    "GrossProfit": [fact("2025-09-28", "2026-09-26", 180 * B, "A-26", "2026-11-03")],
    "OperatingIncomeLoss": [fact("2025-09-28", "2026-09-26", 120 * B, "A-26", "2026-11-03")],
    "NetIncomeLoss": [fact("2025-09-28", "2026-09-26", 100 * B, "A-26", "2026-11-03")],
    "Assets": [fact(None, "2026-09-26", 360 * B, "A-26", "2026-11-03")],
    "Liabilities": [fact(None, "2026-09-26", 300 * B, "A-26", "2026-11-03")],
    "AssetsCurrent": [fact(None, "2026-09-26", 150 * B, "A-26", "2026-11-03")],
    "LiabilitiesCurrent": [fact(None, "2026-09-26", 160 * B, "A-26", "2026-11-03")],
    "StockholdersEquity": [fact(None, "2026-09-26", 60 * B, "A-26", "2026-11-03")],
})
DOC = {"company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026, "report_date": "2026-09-26",
       "filing_date": "2026-11-03", "accession_number": "0000320193-26-000001", "document_url": URL,
       "sections": [
           {"section_id": "1", "section": "Item 1. Business",
            "text": "The Company was incorporated in California in 1977. It designs smartphones and computers."},
           {"section_id": "8", "section": "Item 8. Financial Statements",
            "text": "Report of Independent Registered Public Accounting Firm\nIn our opinion, the consolidated "
                    "financial statements present fairly, in all material respects, the financial position of "
                    "the Company. Also in our opinion, the Company maintained, in all material respects, "
                    "effective internal control over financial reporting.\n/s/ Ernst & Young LLP\n"
                    "We have served as the Company's auditor since 2009."}]}
HITS = [{"id": f"c{i}", "score": 0.6, "text": f"hdr\nApple sells devices and services across many markets {i}.",
         "metadata": {"company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026, "report_date": "2026-09-26",
                      "section": "Item 1. Business", "section_id": "1", "document_url": URL}} for i in range(3)]
LLM_TEXT = ("### BACKGROUND\n- Apple designs devices and services [1].\n### RISKS\n- Intense competition [2].\n"
            "### OUTLOOK\nNOT AVAILABLE")


@pytest.fixture
def world(tmp_path, monkeypatch):
    path = tmp_path / "metrics.csv"
    pd.DataFrame(extract_metrics(APPLE, "AAPL")).to_csv(path, index=False)
    for mod in (financial_service, chat_service, report_service):
        monkeypatch.setattr(mod, "METRICS_PATH", path)
    financial_service._cache.update(mtime=None, df=None)
    (tmp_path / "AAPL_FY2026.json").write_text(json.dumps(DOC), encoding="utf-8")
    (tmp_path / "submissions").mkdir()
    (tmp_path / "submissions" / "CIK0000320193.json").write_text(json.dumps(
        {"name": "Apple Inc.", "sicDescription": "Electronic Computers", "stateOfIncorporation": "CA",
         "exchanges": ["Nasdaq"], "addresses": {"business": {"city": "CUPERTINO", "stateOrCountry": "CA"}}}))
    monkeypatch.setattr(report_service, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(rag_service, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(report_service, "RAW_DIR", tmp_path)
    monkeypatch.setattr(report_service, "search", lambda q, k, **kw: HITS if kw["section_id"] == "1" else [])
    calls = []
    monkeypatch.setattr(report_service, "generate_answer", lambda s, u: calls.append(u) or (LLM_TEXT, "fake-model"))
    return calls


def facts(rep, section_id):
    s = next(s for s in rep["sections"] if s["id"] == section_id)
    return {f["label"]: f for f in s["facts"]}


# ---------- routing ----------
@pytest.mark.parametrize("question", ["Audit report of Apple", "audit report of apple", "Company report on NVIDIA",
                                      "Give me a full report of Microsoft", "financial report for Amazon"])
def test_report_questions(question):
    assert route(question) == {"route": "report", "metrics": []}


@pytest.mark.parametrize("question", ["Who is Apple's auditor?", "What did the auditor's opinion say?",
                                      "What are the risks in Apple's annual report?",
                                      "Summarize NVIDIA's annual report", "Report on Apple's revenue"])
def test_specific_questions_are_not_reports(question):
    assert not wants_report(question)


# ---------- the report ----------
def test_report_has_python_figures_ratios_and_flags(world):
    rep = report_service.build_report("AAPL", use_cache=False)
    assert rep["fiscal_year"] == 2026 and len(world) == 1          # ONE Gemini call for the whole report
    fin = facts(rep, "financials")
    assert fin["Revenue"]["value"] == "$400.00B" and "-20.00% vs FY2025" in fin["Revenue"]["note"]
    assert fin["Total costs and expenses"]["value"] == "$280.00B"   # 400 - 120, by Python
    ratios = facts(rep, "ratios")
    assert ratios["Net profit margin"]["value"] == "25.00%"
    assert ratios["Current ratio"]["value"] == "0.94"
    assert ratios["Debt-to-equity (total liabilities basis)"]["value"] == "5.00"
    flags = facts(rep, "risks")
    assert flags["Declining revenue?"]["value"].endswith("Yes")
    assert flags["Current ratio below 1?"]["value"].endswith("Yes")
    assert facts(rep, "income_statement")["Cost of sales"]["value"] == "$220.00B"


def test_overview_and_sources_come_from_sec_data(world):
    rep = report_service.build_report("AAPL", use_cache=False)
    ov = facts(rep, "overview")
    assert ov["Industry"]["value"] == "Electronic Computers" and ov["Headquarters"]["value"] == "Cupertino, CA"
    assert ov["Established"]["value"] == "1977" and "incorporated in California" in ov["Established"]["note"]
    src = facts(rep, "sources")
    assert src["Auditor"]["value"] == "Ernst & Young LLP" and src["Auditor"]["note"] == "auditor since 2009"
    assert src["Audit opinion: financial statements"]["value"].startswith("Unqualified")
    assert src["Audit opinion: internal control"]["value"] == "Effective"
    assert src["Auditor"]["link"].startswith(URL + "#:~:text=")


def test_missing_parts_are_skipped_not_guessed(world):
    rep = report_service.build_report("AAPL", use_cache=False)
    assert rep["skipped"] == ["9. Future Outlook"]                  # the model said NOT AVAILABLE
    ids = [s["id"] for s in rep["sections"]]
    assert "outlook" not in ids and "background" in ids
    assert "Skipped" not in rep["sections"][1]["text"]
    assert [s["number"] for s in rep["sources"]] == [1, 2]          # only cited passages


def test_report_without_llm_still_has_all_figures(world, monkeypatch):
    def down(*a):
        raise LLMError("quota")
    monkeypatch.setattr(report_service, "generate_answer", down)
    rep = report_service.build_report("AAPL", use_cache=False)
    assert rep["used_llm"] is False
    assert {"2. Company Background", "9. Future Outlook"} <= set(rep["skipped"])
    assert facts(rep, "ratios")["Net profit margin"]["value"] == "25.00%"
    assert "8. Risk Analysis" not in rep["skipped"]                 # Python flags still there


def test_markdown_download(world):
    md = report_service.build_report("AAPL", use_cache=False)["markdown"]
    assert md.startswith("# Apple Inc. (AAPL): Company Report")
    assert "## 6. Financial Ratios" in md and "**Net profit margin:** 25.00%" in md


# ---------- chat + API ----------
def test_chat_report_for_one_company(world):
    res = chat_service.answer_chat("Audit report of Apple", use_cache=False)
    assert res["route"] == "report" and res["report"]["ticker"] == "AAPL"
    assert "9 of 10 sections" in res["answer"]


@pytest.mark.parametrize("question, words", [("Audit report of TCS", "Upload & Analyze"),
                                             ("Company report of Apple and Microsoft", "one company at a time")])
def test_chat_report_without_exactly_one_company(world, question, words):
    res = chat_service.answer_chat(question, use_cache=False)
    assert res["route"] == "report" and res["report"] is None and words in res["answer"]


def test_report_api(world):
    r = client.get("/report/aapl", params={"use_cache": False})
    assert r.status_code == 200 and r.json()["sections"][0]["title"] == "1. Company Overview"
    assert client.get("/report/TSLA").status_code == 404
    assert client.get("/report/AAPL", params={"fiscal_year": 1999}).status_code == 404
    assert client.post("/chat", json={"question": "Audit report of Apple", "use_cache": False}).json()["report"]


@pytest.mark.parametrize("text, year", [
    ("Founded in 1975, we develop and support software, services, devices, and solutions.", "1975"),   # Microsoft
    ("Jeffrey P. Bezos. Mr. Bezos founded Amazon.com in 1994 and has served as Executive Chair.", "1994"),  # Amazon
    ("NVIDIA was incorporated in California in April 1993 and reincorporated in Delaware.", "1993"),
])
def test_established_year_wordings_from_real_10ks(text, year):
    """Real-data check C: the notes' regex only knew 'was incorporated/founded ... in YEAR'."""
    name = {"1975": "Microsoft Corporation", "1994": "Amazon.com, Inc.", "1993": "NVIDIA Corporation"}[year]
    doc = {"sections": [{"section_id": "1", "text": text}]}
    assert report_service.find_established(doc, name).group(1) == year


def test_established_year_ignores_incorporated_by_reference():
    doc = {"sections": [{"section_id": "COVER", "text": "Portions of the proxy statement are incorporated by "
                                                         "reference into Part III. Established hardware offerings."}]}
    assert report_service.find_established(doc, "Apple Inc.") is None      # not stated -> skipped, never guessed


def test_citations_to_missing_sources_are_dropped():
    """Real case from the Level 11 prewarm: an answer built from 5 passages cited [10]."""
    from backend.services.number_guard import drop_unknown_citations
    text = "Operating income rose 16.59% [F]. This suggests improvement [10]. Driven by sales [5][2]."
    assert drop_unknown_citations(text, 5) == "Operating income rose 16.59% [F]. This suggests improvement. Driven by sales [5][2]."
    assert drop_unknown_citations("Revenue was $1B [1].", 0) == "Revenue was $1B."     # numbers route: no sources
