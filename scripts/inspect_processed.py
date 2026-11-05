"""Look at processed 10-Ks.

python -m scripts.inspect_processed              -> summary of every processed report
python -m scripts.inspect_processed AAPL 1A      -> start of Apple's Item 1A (latest year)
"""
import json
import sys

from backend.config import PROCESSED_DIR

PREVIEW_CHARS = 1500


def load_docs() -> list[dict]:
    files = sorted(PROCESSED_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No processed files. Run:  python -m ingestion.extract_documents")
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def summary(docs: list[dict]) -> None:
    for d in docs:
        print(f"\n{d['ticker']} FY{d['fiscal_year']}  (period end {d['report_date']}, "
              f"filed {d['filing_date']})  {d['total_chars']:,} chars")
        print(f"  source: {d['document_url']}")
        for s in d["sections"]:
            print(f"    {s['section_id']:<6}{s['char_count']:>10,}  {s['section'][:70]}")


def preview(docs: list[dict], ticker: str, section_id: str) -> None:
    matches = [d for d in docs if d["ticker"] == ticker.upper()]
    if not matches:
        raise SystemExit(f"No processed report for {ticker}")
    doc = max(matches, key=lambda d: d["report_date"])  # latest year
    for s in doc["sections"]:
        if s["section_id"] == section_id.upper():
            print(f"{doc['ticker']} FY{doc['fiscal_year']} - {s['section']} ({s['char_count']:,} chars)\n")
            print(s["text"][:PREVIEW_CHARS])
            print(f"\n... [source: {doc['document_url']}]")
            return
    print(f"Section {section_id} not found. Available: {[s['section_id'] for s in doc['sections']]}")


if __name__ == "__main__":
    all_docs = load_docs()
    if len(sys.argv) == 3:
        preview(all_docs, sys.argv[1], sys.argv[2])
    else:
        summary(all_docs)
