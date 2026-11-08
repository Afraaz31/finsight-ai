"""Level 10: answers carry the data itself, plus exact-spot links and full sections.

No model, no internet: uses the processed 10-K files from Level 1 and fake hits.
"""
import json
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app
from backend.services import filing_service, rag_service
from backend.services.source_links import deep_link, pick_anchor_sentence

client = TestClient(app)
URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl-20260926.htm"


# ---------- exact-spot links ----------
def test_deep_link_points_at_a_prose_sentence():
    passage = ("Total net sales | 478,830 | 416,161\n"
               "In our opinion, the financial statements present fairly, in all material respects, "
               "the financial position of Apple Inc. at the end of the year.")
    link = deep_link(URL, passage)
    assert link.startswith(URL + "#:~:text=")
    start, end = map(unquote, link.split("#:~:text=")[1].split(","))
    assert start == "In our opinion, the financial"   # skipped the table row
    assert end == "position of Apple Inc."             # sentence ends at "Inc." - still exact page text


def test_deep_link_encodes_special_characters():
    link = deep_link(URL, "Our long-term auditor Ernst & Young LLP has served the company since the year it began.")
    fragment = link.split("#:~:text=")[1]
    assert "&" not in fragment and "%26" in fragment     # "&" would break the fragment
    assert "%2D" in fragment                              # "-" too
    assert fragment.count(",") == 1                       # the only raw comma separates start and end


def test_deep_link_strips_bullets_and_skips_headings():
    """Real-data check B: bullets glued to the first word and ALL-CAPS headings broke ~5% of the anchors."""
    passage = ("ITEM 7.MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS\n"
               "•changes in product development cycles and time to market for our new products;")
    start, end = map(unquote, deep_link(URL, passage).split("#:~:text=")[1].split(","))
    assert start == "changes in product development cycles" and end == "for our new products;"
    assert pick_anchor_sentence("(1)Services net sales include amortization of the deferred value of services.") \
        .startswith("Services net sales")


def test_deep_link_falls_back_to_plain_url():
    assert deep_link(URL, "Net sales | 1 | 2") == URL     # only a table row -> no anchor
    assert pick_anchor_sentence("") is None


# ---------- audit questions go to the right chapters ----------
@pytest.mark.parametrize("question", ["Find the audit report of Apple", "Who is Apple's auditor?",
                                      "What did the independent registered public accounting firm say?"])
def test_audit_questions_search_item_8_and_9a(question):
    assert rag_service.detect_sections(question) == ["8", "9A", "15"]   # NVIDIA keeps its statements in Item 15


def test_audit_retrieval_pools_sections_and_adds_the_auditor_signature(monkeypatch):
    """Real-data check C: NVIDIA's Item 8 is a pointer (not indexed), its report is in Item 15, and
    "who audits X?" never ranked the "/s/PricewaterhouseCoopers LLP" block. Search 8+9A+15 as one pool and
    always fetch the signature block by its fixed wording."""
    calls = []

    def fake_search(question, k=5, ticker=None, section_id=None, fiscal_year=None, collection_name=None,
                    doc_id=None, contains=None):
        calls.append({"section_id": section_id, "contains": contains})
        name = "signature" if contains else "opinion"
        return [{"id": name, "text": f"h\n{name}", "score": 0.6, "metadata": {}}]
    monkeypatch.setattr(rag_service, "search", fake_search)
    hits = rag_service.retrieve("Who audits NVIDIA?", ["NVDA"])
    assert [h["id"] for h in hits] == ["signature", "opinion"]
    assert calls == [{"section_id": ["8", "9A", "15"], "contains": None},
                     {"section_id": ["8", "9A", "15"], "contains": "auditor since"}]   # no whole-report fallback


def test_annual_report_means_summary_sections():
    assert rag_service.detect_sections("Show me Apple's annual report") == rag_service.SUMMARY_SECTIONS
    assert rag_service.detect_sections("What are the risks in Apple's annual report?") == ["1A"]


def test_prompt_demands_the_data_in_the_answer():
    assert "Never answer only by telling the user to look at the document" in rag_service.SYSTEM_PROMPT


def test_sources_carry_full_text_section_and_deep_link():
    body = "In our opinion, the consolidated financial statements present fairly the financial position. " * 6
    hit = {"id": "a", "score": 0.7, "text": "Apple Inc. | FY2026 | Item 8\n" + body,
           "metadata": {"company": "Apple Inc.", "ticker": "AAPL", "fiscal_year": 2026, "report_date": "2026-09-26",
                        "section": "Item 8. Financial Statements", "section_id": "8", "document_url": URL}}
    [src] = rag_service.format_sources([hit], "Apple's auditor gave an unqualified opinion [1].")
    assert src["text"] == body and len(src["excerpt"]) == 300
    assert src["section_id"] == "8"
    assert src["deep_link"].startswith(URL + "#:~:text=In%20our%20opinion")


# ---------- full section endpoint ----------
@pytest.fixture
def processed(tmp_path, monkeypatch):
    doc = {"company": "Apple Inc.", "report_date": "2026-09-26", "document_url": URL,
           "sections": [{"section_id": "8", "section": "Item 8. Financial Statements",
                         "text": "Report of Independent Registered Public Accounting Firm\nIn our opinion ..."},
                        {"section_id": "9A", "section": "Item 9A. Controls and Procedures", "text": "Controls ..."}]}
    (tmp_path / "AAPL_FY2026.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(filing_service, "PROCESSED_DIR", tmp_path)
    return tmp_path


def test_section_endpoint_returns_full_text(processed):
    r = client.get("/sec/section", params={"ticker": "aapl", "fiscal_year": 2026, "section_id": "8"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"].startswith("Report of Independent Registered Public Accounting Firm")
    assert body["section"] == "Item 8. Financial Statements" and body["document_url"] == URL


def test_sections_list(processed):
    r = client.get("/sec/sections", params={"ticker": "AAPL", "fiscal_year": 2026})
    assert [s["section_id"] for s in r.json()] == ["8", "9A"]


@pytest.mark.parametrize("params, status", [
    ({"ticker": "AAPL", "fiscal_year": 2026, "section_id": "99"}, 404),   # no such section
    ({"ticker": "AAPL", "fiscal_year": 1999, "section_id": "8"}, 404),    # no such report
    ({"ticker": "TSLA", "fiscal_year": 2026, "section_id": "8"}, 404),    # unsupported company
    ({"ticker": "AAPL", "fiscal_year": "abc", "section_id": "8"}, 422),   # bad input
])
def test_section_endpoint_errors(processed, params, status):
    assert client.get("/sec/section", params=params).status_code == status


def test_real_processed_reports_have_item_8_when_present():
    """On the real data, every processed 10-K's financial statements can be served in full.

    NVIDIA's Item 8 is a one-line pointer ("...set forth in our Consolidated Financial Statements") and the
    statements sit in Item 15 - exactly why audit questions search Item 8 + 9A + 15.
    """
    files = sorted(config.PROCESSED_DIR.glob("*_FY*.json"))
    if not files:
        pytest.skip("No processed reports in this environment.")
    for path in files:
        ticker, year = path.stem.split("_FY")
        ids = [s["section_id"] for s in filing_service.list_sections(ticker, int(year))]
        if "8" in ids:
            item8 = filing_service.get_section(ticker, int(year), "8")["char_count"]
            item15 = filing_service.get_section(ticker, int(year), "15")["char_count"] if "15" in ids else 0
            assert item8 > 1000 or item15 > 1000, path.name
