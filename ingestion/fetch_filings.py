"""Level 1, step 1: find each company's latest 10-K filings and download them.

Run from the project root:  python -m ingestion.fetch_filings
"""
import json
import logging

from backend.companies import COMPANIES
from backend.config import PROJECT_ROOT, RAW_DIR
from ingestion.sec_client import SECRequestError, fetch_json, fetch_to_file

log = logging.getLogger(__name__)

REPORTS_PER_COMPANY = 2
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/"
MANIFEST_PATH = RAW_DIR / "filings_manifest.json"


def select_latest_10ks(submissions: dict, count: int = REPORTS_PER_COMPANY) -> list[dict]:
    """Pick the newest `count` original 10-K filings (no amendments) from a submissions JSON."""
    recent = submissions["filings"]["recent"]
    picked = []
    for i, form in enumerate(recent["form"]):
        if form != "10-K":            # skips 10-K/A amendments, 10-Q, 8-K, ...
            continue
        if not recent["primaryDocument"][i]:
            continue                  # no main document listed -> nothing to download
        picked.append({
            "accession_number": recent["accessionNumber"][i],
            "filing_date": recent["filingDate"][i],
            "report_date": recent["reportDate"][i],
            "primary_document": recent["primaryDocument"][i],
        })
    picked.sort(key=lambda f: f["filing_date"], reverse=True)  # newest first
    return picked[:count]


def build_filing_record(ticker: str, company: dict, filing: dict) -> dict:
    """Add URLs, fiscal year and local file path to one selected filing."""
    acc_nodash = filing["accession_number"].replace("-", "")
    base_url = ARCHIVE_BASE.format(cik_int=int(company["cik"]), acc_nodash=acc_nodash)
    report_date = filing["report_date"]
    local_path = RAW_DIR / "filings" / ticker / f"{filing['accession_number']}.htm"
    return {
        "company": company["name"],
        "ticker": ticker,
        "cik": company["cik"],
        "form": "10-K",
        **filing,
        "fiscal_year": int(report_date[:4]) if report_date else None,
        "document_url": base_url + filing["primary_document"],
        "filing_index_url": base_url,
        "local_path": local_path.relative_to(PROJECT_ROOT).as_posix(),
    }


def fetch_company_filings(ticker: str, company: dict) -> list[dict]:
    """Get one company's latest 10-Ks: read the filing list, then download each report."""
    submissions = fetch_json(
        SUBMISSIONS_URL.format(cik=company["cik"]),
        RAW_DIR / "submissions" / f"CIK{company['cik']}.json",
        max_age_hours=24,
    )
    records = []
    for filing in select_latest_10ks(submissions):
        record = build_filing_record(ticker, company, filing)
        try:
            fetch_to_file(record["document_url"], PROJECT_ROOT / record["local_path"])
            records.append(record)
        except SECRequestError as exc:
            log.error("Could not download %s %s: %s", ticker, filing["accession_number"], exc)
    return records


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    manifest, failed = [], []

    for ticker, company in COMPANIES.items():
        log.info("=== %s (%s) ===", company["name"], ticker)
        try:
            records = fetch_company_filings(ticker, company)
        except SECRequestError as exc:
            log.error("Could not get the filing list for %s: %s", ticker, exc)
            failed.append(ticker)
            continue
        if len(records) < REPORTS_PER_COMPANY:
            log.warning("%s: expected %d reports, got %d", ticker, REPORTS_PER_COMPANY, len(records))
        manifest.extend(records)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\n{'Ticker':<7}{'FY':<7}{'Period end':<12}{'Filed':<12}Document")
    for r in manifest:
        print(f"{r['ticker']:<7}{r['fiscal_year']!s:<7}{r['report_date']:<12}"
              f"{r['filing_date']:<12}{r['primary_document']}")
    print(f"\n{len(manifest)} reports saved. Manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    if failed:
        print(f"FAILED companies: {', '.join(failed)} (rerun later; cached files are kept)")


if __name__ == "__main__":
    main()
