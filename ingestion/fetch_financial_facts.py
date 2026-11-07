"""Level 7, ingestion: download SEC Company Facts for each company and build metrics.csv.

Run from the project root:  python -m ingestion.fetch_financial_facts
"""
import logging

import pandas as pd

from backend.companies import COMPANIES
from backend.config import METRICS_PATH, RAW_DIR
from backend.services.financial_service import METRICS, extract_metrics, format_money
from ingestion.sec_client import SECRequestError, fetch_json

log = logging.getLogger(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    rows, failed = [], []
    for ticker, company in COMPANIES.items():
        try:
            facts = fetch_json(FACTS_URL.format(cik=company["cik"]),
                               RAW_DIR / "companyfacts" / f"CIK{company['cik']}.json", max_age_hours=24)
        except SECRequestError as exc:
            log.error("Could not get Company Facts for %s: %s", ticker, exc)
            failed.append(ticker)
            continue
        company_rows = extract_metrics(facts, ticker)
        log.info("%-5s %d values", ticker, len(company_rows))
        rows.extend(company_rows)

    if not rows:
        raise SystemExit("No financial data extracted.")
    df = pd.DataFrame(rows)
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(METRICS_PATH, index=False)

    latest = df.sort_values("period_end").groupby(["ticker", "metric"]).tail(1)
    table = latest.pivot(index="metric", columns="ticker", values="value").reindex(list(METRICS))
    print("\nLatest fiscal year values:")
    print(table.apply(lambda col: col.map(lambda v: format_money(v) if pd.notna(v) else "not reported")).to_string())
    fy = latest[latest["metric"] == "revenue"].set_index("ticker")[["fiscal_year", "period_end"]]
    print("\nLatest fiscal year per company (revenue):\n" + fy.to_string())
    derived = df[df["derived"]]
    if not derived.empty:
        print(f"\nDerived values (liabilities = total liabilities & equity - equity): "
              f"{sorted(derived['ticker'].unique())}")
    print(f"\n{len(df)} rows written to {METRICS_PATH}")
    if failed:
        print(f"FAILED: {', '.join(failed)} (rerun later)")


if __name__ == "__main__":
    main()
