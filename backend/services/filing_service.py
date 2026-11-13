"""Read full 10-K sections from the processed reports (Level 1 output), for "Read the full section"."""
import json

from backend.companies import COMPANIES
from backend.config import PROCESSED_DIR
from backend.services.financial_service import UnknownCompany


class SectionNotFound(Exception):
    """No such report or section (the API turns this into HTTP 404)."""


def _load(ticker: str, fiscal_year: int) -> dict:
    ticker = ticker.upper()
    if ticker not in COMPANIES:
        raise UnknownCompany(f"Unsupported ticker '{ticker}'.")
    path = PROCESSED_DIR / f"{ticker}_FY{int(fiscal_year)}.json"
    if not path.exists():
        raise SectionNotFound(f"No processed 10-K for {ticker} FY{fiscal_year}.")
    return json.loads(path.read_text(encoding="utf-8"))


def list_sections(ticker: str, fiscal_year: int) -> list[dict]:
    doc = _load(ticker, fiscal_year)
    return [{"section_id": s["section_id"], "section": s["section"], "char_count": len(s["text"])}
            for s in doc["sections"]]


def get_section(ticker: str, fiscal_year: int, section_id: str) -> dict:
    """The full text of one 10-K section, with its source link."""
    doc = _load(ticker, fiscal_year)
    for s in doc["sections"]:
        if s["section_id"].upper() == section_id.upper():
            return {"ticker": ticker.upper(), "company": doc.get("company", ticker), "fiscal_year": int(fiscal_year),
                    "period_end": doc.get("report_date", ""), "section_id": s["section_id"],
                    "section": s["section"], "text": s["text"], "char_count": len(s["text"]),
                    "document_url": doc.get("document_url", "")}
    raise SectionNotFound(f"Section '{section_id}' not found in {ticker.upper()} FY{fiscal_year}.")
