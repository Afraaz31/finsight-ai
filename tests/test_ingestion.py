"""Level 1 tests: ingestion logic with small fake inputs (no internet needed)."""
from bs4 import BeautifulSoup

from ingestion.extract_documents import clean_html, normalize_text, split_into_sections, table_to_text
from ingestion.fetch_filings import select_latest_10ks


def test_select_latest_10ks_skips_amendments_and_other_forms():
    submissions = {"filings": {"recent": {
        "form":            ["8-K", "10-K/A", "10-K", "10-Q", "10-K", "10-K"],
        "accessionNumber": ["a", "b", "c", "d", "e", "f"],
        "filingDate":      ["2026-12-01", "2026-11-20", "2026-11-03", "2026-08-01", "2025-10-31", "2024-11-01"],
        "reportDate":      ["", "2026-09-26", "2026-09-26", "2026-06-27", "2025-09-27", "2024-09-28"],
        "primaryDocument": ["x.htm", "y.htm", "c.htm", "d.htm", "e.htm", "f.htm"],
    }}}
    picked = select_latest_10ks(submissions, count=2)
    assert [f["accession_number"] for f in picked] == ["c", "e"]


def test_table_to_text_merges_dollar_signs_and_brackets():
    html = "<table><tr><td>Net sales</td><td>$</td><td>391,035</td><td>(</td><td>1,234</td><td>)</td></tr></table>"
    table = BeautifulSoup(html, "lxml").find("table")
    assert table_to_text(table) == "Net sales | $391,035 | (1,234)"


def test_clean_html_removes_scripts_and_hidden_xbrl():
    html = b"""<html><head><style>p {color: red}</style></head><body>
    <div style="display:none">HIDDEN XBRL FACTS</div>
    <script>alert(1)</script>
    <p>Apple <b>designs</b> phones.</p>
    </body></html>"""
    text = clean_html(html)
    assert "Apple designs phones." in text
    assert "HIDDEN" not in text
    assert "alert" not in text


def test_split_into_sections_keeps_body_not_table_of_contents():
    toc = "\n".join([
        "Item 1. | Business | 1",
        "Item 1A. | Risk Factors | 5",
        "Item 7. | MD&A | 20",
        "Item 8. | Financial Statements | 30",
        "Item 9A. | Controls | 40",
    ])
    body = "\n".join([
        "Item 1. Business", "We make phones. " * 50,
        "Item 1A. Risk Factors", "Supply chain risk. " * 50,
        "Item 7. Management's Discussion and Analysis", "Revenue grew. " * 50,
        "Item 8. Financial Statements", "Balance sheet. " * 50,
        "Item 9A. Controls and Procedures", "Controls are effective. " * 50,
    ])
    sections = split_into_sections("Cover text\n" + toc + "\n" + body)
    by_id = {s["section_id"]: s for s in sections}
    assert "Supply chain risk." in by_id["1A"]["text"]
    assert by_id["1A"]["section"] == "Item 1A. Risk Factors"
    assert "COVER" in by_id


def test_split_into_sections_falls_back_to_full_document():
    sections = split_into_sections("Just some text without any item headings.")
    assert len(sections) == 1
    assert sections[0]["section_id"] == "FULL"


# ---------- Regression tests for bugs found on the real filings ----------

def test_heading_without_space_after_period_is_found():
    """Alphabet writes 'ITEM 1A.RISK FACTORS' (no space). It must still count as a heading."""
    toc = "\n".join(f"Item {i}. | Title | {n}" for n, i in enumerate(["1", "1A", "7", "8", "9A"]))
    body = "\n".join([
        "ITEM 1.BUSINESS", "Search and ads. " * 50,
        "ITEM 1A.RISK FACTORS", "Regulatory risk. " * 50,
        "ITEM 7.MANAGEMENT'S DISCUSSION", "Revenue grew. " * 50,
        "ITEM 8.FINANCIAL STATEMENTS", "Balance sheet. " * 50,
        "ITEM 9A.CONTROLS AND PROCEDURES", "Effective. " * 50,
    ])
    by_id = {s["section_id"]: s for s in split_into_sections(toc + "\n" + body)}
    assert "Regulatory risk." in by_id["1A"]["text"]
    assert len(by_id["1A"]["text"]) > 500  # the real section, not the one-line TOC entry


def test_repeated_page_headers_do_not_cut_a_section():
    """Microsoft repeats 'Item 1A' at the top of every page; the whole section must be kept."""
    pages = "\n".join(line for p in range(5) for line in ("Item 1A", f"Risk page {p}. " * 40))
    text = "\n".join([
        "Item 1. Business", "We make software. " * 50,
        "ITEM 1A. RISK FACTORS", pages,
        "Item 7. MD&A", "Revenue grew. " * 50,
        "Item 8. Financial Statements", "Balance sheet. " * 50,
        "Item 9A. Controls", "Effective. " * 50,
    ])
    by_id = {s["section_id"]: s for s in split_into_sections(text)}
    risk = by_id["1A"]["text"]
    assert all(f"Risk page {p}." in risk for p in range(5))


def test_normalize_text_drops_page_footers_with_changing_page_numbers():
    """Apple's footer 'Apple Inc. | 2026 Form 10-K | N' changes N every page; all copies must go."""
    lines = []
    for page in range(1, 21):
        lines += [f"Real sentence number {page} about the business.", f"Apple Inc. | 2026 Form 10-K | {page}"]
    text = normalize_text("\n".join(lines))
    assert "Form 10-K |" not in text
    assert "Real sentence number 20 about the business." in text
