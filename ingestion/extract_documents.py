"""Level 1, step 2: turn raw 10-K HTML into clean text, split by 10-K Item sections.

Run from the project root:  python -m ingestion.extract_documents
Add --force to re-process reports that were already processed.
"""
import argparse
import json
import logging
import re
import warnings
from collections import Counter

from bs4 import BeautifulSoup, Comment, NavigableString, XMLParsedAsHTMLWarning

from backend.config import PROCESSED_DIR, PROJECT_ROOT
from ingestion.fetch_filings import MANIFEST_PATH

log = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)  # 10-Ks are XHTML; harmless

# ---------- 10-K structure ----------
ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities",
    "6": "[Reserved]",
    "7": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management and Related Stockholder Matters",
    "13": "Certain Relationships and Related Transactions, and Director Independence",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}
ITEM_ORDER = list(ITEM_TITLES)

# A heading line starts with "Item 1A." / "ITEM 7 -" / "Item 10:" / "ITEM 2.PROPERTIES" / "Item 1 Business".
# The number must be followed by punctuation or a title, so a bare "Item 1A" line
# (a running page header, as in Microsoft's 10-K) is NOT treated as a heading.
ITEM_HEADING = re.compile(r"^item\s+(1[0-6]|[1-9][abc]?)(?:\s*[.:\-–—]|\s+(?=\S))", re.IGNORECASE)
MAX_HEADING_LENGTH = 200   # longer lines are paragraphs, not headings
MIN_ITEMS_FOUND = 5        # fewer matches -> keep the document as one section

# ---------- cleaning settings ----------
BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "ul", "ol"]
HIDDEN_STYLE = re.compile(r"display\s*:\s*none", re.IGNORECASE)
PAGE_NUMBER = re.compile(r"(?:page\s+)?-?\s*\d{1,3}\s*-?|[ivxl]{1,6}", re.IGNORECASE)
BARE_ITEM_LINE = re.compile(r"item\s+\d{1,2}[abc]?", re.IGNORECASE)  # running page header, e.g. "Item 1A"
TRAILING_PAGE_NUMBER = re.compile(r"\s*\|?\s*\d{1,3}$")  # "Apple Inc. | 2026 Form 10-K | 5" -> footer key
REPEATED_LINE_MIN = 15     # a short line repeated this often is a page header/footer
SHORT_DOC_WARNING = 50_000 # fewer characters than this probably means extraction went wrong


def _remove(tags) -> None:
    """Delete tags from the tree (skipping ones already deleted with a parent)."""
    for tag in tags:
        if not tag.decomposed:
            tag.decompose()


def _merge_symbol_cells(cells: list[str]) -> list[str]:
    """Glue '$' and '(' to the next cell and ')' / '%' to the previous one."""
    merged = []
    for cell in cells:
        if merged and cell in (")", "%", ")%"):
            merged[-1] += cell
        elif merged and merged[-1] in ("$", "(", "$("):
            merged[-1] += cell
        else:
            merged.append(cell)
    return merged


def table_to_text(table) -> str:
    """Convert an HTML table into lines of 'cell | cell | cell'."""
    lines = []
    for row in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        cells = _merge_symbol_cells([c for c in cells if c])
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _footer_key(line: str) -> str:
    """The line without its trailing page number, so footers on different pages compare equal."""
    key = TRAILING_PAGE_NUMBER.sub("", line)
    return key if len(key) >= 10 else line  # short keys ("Total") could be real table rows


def normalize_text(text: str) -> str:
    """Tidy whitespace and drop page numbers and repeated header/footer lines."""
    text = text.replace("\xa0", " ").replace("​", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines
             if line and not PAGE_NUMBER.fullmatch(line) and not BARE_ITEM_LINE.fullmatch(line)]
    counts = Counter(_footer_key(line) for line in lines if len(line) <= 80)
    repeated = {key for key, n in counts.items() if n >= REPEATED_LINE_MIN}
    return "\n".join(line for line in lines if _footer_key(line) not in repeated)


def clean_html(html: bytes) -> str:
    """Raw 10-K HTML -> readable plain text."""
    soup = BeautifulSoup(html, "lxml")

    # 1. Remove things that are not visible text.
    _remove(soup.find_all(["script", "style", "head", "ix:header"]))
    _remove(soup.find_all(style=HIDDEN_STYLE))
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # 2. Collapse whitespace inside text pieces (HTML source line-wraps are not real breaks).
    for piece in soup.find_all(string=True):
        if type(piece) is NavigableString and re.search(r"\s{2,}|[\n\t]", piece):
            piece.replace_with(re.sub(r"\s+", " ", piece))

    # 3. Tables -> "a | b | c" lines.
    for table in soup.find_all("table"):
        table.replace_with(soup.new_string("\n" + table_to_text(table) + "\n"))

    # 4. Line breaks only at block-level tags.
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")

    return normalize_text(soup.get_text())


def split_into_sections(text: str) -> list[dict]:
    """Split 10-K text into Item sections, ignoring the table of contents."""
    lines = text.split("\n")
    marks = []  # (line number, item id)
    for i, line in enumerate(lines):
        if len(line) > MAX_HEADING_LENGTH:
            continue
        match = ITEM_HEADING.match(line)
        if match and match.group(1).upper() in ITEM_TITLES:
            item_id = match.group(1).upper()
            if marks and marks[-1][1] == item_id:
                continue  # same Item again right away = page header / continuation, not a new section
            marks.append((i, item_id))

    if len(marks) < MIN_ITEMS_FOUND:
        return [{"section_id": "FULL", "section": "Full Document", "text": text}]

    # Cut at every heading; for each Item keep the LONGEST piece (the real section, not the TOC line).
    best = {}
    for n, (start, item_id) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if len(body) > len(best.get(item_id, "")):
            best[item_id] = body

    sections = []
    cover = "\n".join(lines[: marks[0][0]]).strip()
    if cover:
        sections.append({"section_id": "COVER", "section": "Cover Page", "text": cover})
    for item_id in ITEM_ORDER:
        if item_id in best:
            sections.append({
                "section_id": item_id,
                "section": f"Item {item_id}. {ITEM_TITLES[item_id]}",
                "text": best[item_id],
            })
    return sections


def output_path_for(record: dict):
    label = f"FY{record['fiscal_year']}" if record["fiscal_year"] else record["accession_number"]
    return PROCESSED_DIR / f"{record['ticker']}_{label}.json"


def process_record(record: dict) -> dict:
    """Clean and split one downloaded report; return the processed document."""
    raw_path = PROJECT_ROOT / record["local_path"]
    text = clean_html(raw_path.read_bytes())
    sections = split_into_sections(text)
    for s in sections:
        s["char_count"] = len(s["text"])
    total = sum(s["char_count"] for s in sections)
    if total < SHORT_DOC_WARNING:
        log.warning("%s FY%s is only %d characters - check the source file",
                    record["ticker"], record["fiscal_year"], total)
    return {**record, "total_chars": total, "section_count": len(sections), "sections": sections}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean downloaded 10-Ks into sectioned JSON.")
    parser.add_argument("--force", action="store_true", help="re-process already processed reports")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    if not MANIFEST_PATH.exists():
        raise SystemExit("No manifest found. Run first:  python -m ingestion.fetch_filings")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    for record in manifest:
        out_path = output_path_for(record)
        if out_path.exists() and not args.force:
            log.info("Already processed  %s", out_path.name)
            continue
        if not (PROJECT_ROOT / record["local_path"]).exists():
            log.error("Missing raw file for %s FY%s: %s (rerun fetch_filings)",
                      record["ticker"], record["fiscal_year"], record["local_path"])
            continue
        log.info("Processing %s FY%s ...", record["ticker"], record["fiscal_year"])
        doc = process_record(record)
        out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        found = [s["section_id"] for s in doc["sections"]]
        log.info("  -> %s: %d sections, %d chars  %s",
                 out_path.name, doc["section_count"], doc["total_chars"], found)


if __name__ == "__main__":
    main()
