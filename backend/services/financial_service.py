"""Level 7: exact financial figures from SEC XBRL "Company Facts", compared with Pandas.

Two halves:
  1. EXTRACT (used by ingestion/fetch_financial_facts.py): raw Company Facts JSON -> one clean
     row per company x metric x fiscal year, with the filing it came from.
  2. SERVE (used by the API and chat): load data/financial/metrics.csv, look up values,
     compare companies, compute differences and percentages.

The LLM never produces these numbers. It may only explain them.
"""
import logging
from datetime import date

import pandas as pd

from backend.companies import COMPANIES
from backend.config import FINANCIAL_YEARS_KEPT, METRICS_PATH

log = logging.getLogger(__name__)

# Each metric: which XBRL tags can hold it, in order of preference. Companies use different tags,
# and some switched tags over the years, so for EACH year we use the best tag that has a value.
METRICS = {
    "revenue": {"label": "Revenue", "type": "duration",
                "tags": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                         "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]},
    "gross_profit": {"label": "Gross profit", "type": "duration", "tags": ["GrossProfit"]},
    "operating_income": {"label": "Operating income", "type": "duration", "tags": ["OperatingIncomeLoss"]},
    "net_income": {"label": "Net income", "type": "duration", "tags": ["NetIncomeLoss", "ProfitLoss"]},
    "operating_cash_flow": {"label": "Operating cash flow", "type": "duration",
                            "tags": ["NetCashProvidedByUsedInOperatingActivities"]},
    "total_assets": {"label": "Total assets", "type": "instant", "tags": ["Assets"]},
    "total_liabilities": {"label": "Total liabilities", "type": "instant", "tags": ["Liabilities"]},
    "cash": {"label": "Cash and cash equivalents", "type": "instant",
             "tags": ["CashAndCashEquivalentsAtCarryingValue"]},
}


class UnknownCompany(Exception):
    """Ticker not supported (the API turns this into HTTP 404).

    Not a subclass of LookupError on purpose: KeyError is a LookupError, and a real bug
    (a KeyError) must stay a 500, not look like a harmless 404.
    """


EQUITY_TAGS = ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"]


# =====================================================================
# 1. EXTRACT: Company Facts JSON -> clean annual rows
# =====================================================================
def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def annual_facts(facts_json: dict, tag: str, period_type: str) -> list[dict]:
    """The as-originally-reported annual values of one XBRL tag, one per fiscal year.

    Rules (each one avoids a real trap in SEC data):
    - only original annual reports: form "10-K" and fp "FY" (no 10-K/A amendments, no 10-Q)
    - duration metrics must cover ~one year (350-380 days); 10-Ks also contain quarterly numbers
    - every 10-K repeats LAST year's numbers for comparison, so per filing we keep only the fact
      with the LATEST end date = that filing's own fiscal year
    - if two filings still give the same period, keep the earliest filed (the original report)
    """
    entries = (facts_json.get("facts", {}).get("us-gaap", {}).get(tag, {})
               .get("units", {}).get("USD", []))
    current_by_filing = {}
    for fact in entries:
        if fact.get("form") != "10-K" or fact.get("fp") != "FY":
            continue
        if period_type == "duration":
            if not fact.get("start") or not 350 <= _days(fact["start"], fact["end"]) <= 380:
                continue
        elif fact.get("start"):          # balance-sheet values are a single date, no start
            continue
        best = current_by_filing.get(fact["accn"])
        if best is None or fact["end"] > best["end"]:
            current_by_filing[fact["accn"]] = fact

    by_period = {}
    for fact in current_by_filing.values():
        kept = by_period.get(fact["end"])
        if kept is None or fact["filed"] < kept["filed"]:
            by_period[fact["end"]] = fact
    return sorted(by_period.values(), key=lambda f: f["end"])


def _row(ticker: str, metric: str, fact: dict, tag: str, derived: bool = False) -> dict:
    company = COMPANIES[ticker]
    accn = fact["accn"]
    return {
        "ticker": ticker, "company": company["name"], "metric": metric,
        "label": METRICS[metric]["label"], "fiscal_year": int(fact["end"][:4]),
        "period_start": fact.get("start", ""), "period_end": fact["end"],
        "value": float(fact["val"]), "unit": "USD", "tag": tag, "derived": derived,
        "form": fact["form"], "accession": accn, "filed": fact["filed"],
        "source_url": f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{accn.replace('-', '')}/",
    }


def extract_metrics(facts_json: dict, ticker: str) -> list[dict]:
    """All metrics for one company, most recent FINANCIAL_YEARS_KEPT years each."""
    rows = []
    for metric, spec in METRICS.items():
        by_end = {}
        for tag in spec["tags"]:                         # best tag first
            for fact in annual_facts(facts_json, tag, spec["type"]):
                by_end.setdefault(fact["end"], _row(ticker, metric, fact, tag))

        if metric == "total_liabilities":                # some companies (e.g. Amazon) don't tag it
            totals = {f["end"]: f for f in annual_facts(facts_json, "LiabilitiesAndStockholdersEquity", "instant")}
            equity = {}
            for tag in reversed(EQUITY_TAGS):            # preferred tag overwrites
                equity.update({f["end"]: f for f in annual_facts(facts_json, tag, "instant")})
            for end, total in totals.items():
                if end not in by_end and end in equity:
                    fact = {**total, "val": float(total["val"]) - float(equity[end]["val"])}
                    by_end[end] = _row(ticker, metric, fact,
                                       "LiabilitiesAndStockholdersEquity - StockholdersEquity", derived=True)

        latest = sorted(by_end.values(), key=lambda r: r["period_end"])[-FINANCIAL_YEARS_KEPT:]
        rows.extend(latest)

    # A metric whose newest value is old is NOT the company's current figure. Real example: Amazon
    # tagged GrossProfit only in its FY2009 10-K. Showing that as Amazon's "latest" gross profit next
    # to other companies' FY2026 values would mislead, so such a metric counts as not reported.
    if rows:
        newest = max(r["fiscal_year"] for r in rows)
        last_year = {}
        for r in rows:
            last_year[r["metric"]] = max(last_year.get(r["metric"], 0), r["fiscal_year"])
        stale = {m for m, fy in last_year.items() if fy < newest - 1}
        for m in sorted(stale):
            log.info("%s: %s was last reported for FY%d, so it is treated as not reported",
                     ticker, m, last_year[m])
        rows = [r for r in rows if r["metric"] not in stale]
    return rows


# =====================================================================
# 2. SERVE: look up and compare
# =====================================================================
_cache = {"mtime": None, "df": None}


def load_metrics() -> pd.DataFrame:
    """metrics.csv as a DataFrame (re-read automatically when the file changes)."""
    if not METRICS_PATH.exists():
        raise RuntimeError("Financial data not built yet. Run: python -m ingestion.fetch_financial_facts")
    mtime = METRICS_PATH.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache["df"] = pd.read_csv(METRICS_PATH, dtype={"period_start": str, "period_end": str})
        _cache["mtime"] = mtime
    return _cache["df"]


def check_metric(metric: str) -> str:
    if metric not in METRICS:
        raise ValueError(f"Unknown metric '{metric}'. Available: {', '.join(METRICS)}")
    return metric


def format_money(value: float) -> str:
    """478834000000 -> '$478.83B'   -2300000000 -> '-$2.30B'   850000000 -> '$850.0M'"""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e9:
        return f"{sign}${v / 1e9:,.2f}B"
    if v >= 1e6:
        return f"{sign}${v / 1e6:,.1f}M"
    return f"{sign}${v:,.0f}"


def _clean(row: dict) -> dict:
    row = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()}
    row["value_display"] = format_money(row["value"])
    row["derived"] = bool(row["derived"])
    row["fiscal_year"] = int(row["fiscal_year"])
    return row


def history(ticker: str, metric: str) -> list[dict]:
    df = load_metrics()
    part = df[(df["ticker"] == ticker.upper()) & (df["metric"] == check_metric(metric))]
    rows = [_clean(r) for r in part.sort_values("period_end").to_dict(orient="records")]
    for prev, cur in zip(rows, rows[1:]):                 # year-over-year change, done by Python
        cur["yoy_change"] = cur["value"] - prev["value"]
        cur["yoy_change_pct"] = round((cur["value"] / prev["value"] - 1) * 100, 2) if prev["value"] else None
    return rows


def value_for(ticker: str, metric: str, fiscal_year: int | None = None) -> dict | None:
    """Latest value (or a specific fiscal year). None if the company doesn't report it."""
    rows = history(ticker, metric)
    if fiscal_year:
        rows = [r for r in rows if r["fiscal_year"] == int(fiscal_year)]
    return rows[-1] if rows else None


def company_financials(ticker: str) -> dict:
    ticker = ticker.upper()
    if ticker not in COMPANIES:
        raise UnknownCompany(f"Unsupported ticker '{ticker}'. Supported: {', '.join(COMPANIES)}")
    metrics = []
    for metric, spec in METRICS.items():
        rows = history(ticker, metric)
        metrics.append({"metric": metric, "label": spec["label"],
                        "latest": rows[-1] if rows else None, "history": rows})
    return {"ticker": ticker, "company": COMPANIES[ticker]["name"], "metrics": metrics}


def compare(tickers: list[str], metric: str, fiscal_year: int | None = None) -> dict:
    """Compare one metric across companies: ranking, differences, percentages, period notes."""
    label = METRICS[check_metric(metric)]["label"]
    rows, notes = [], []
    for ticker in dict.fromkeys(t.upper() for t in tickers):
        if ticker not in COMPANIES:
            raise UnknownCompany(f"Unsupported ticker '{ticker}'.")
        row = value_for(ticker, metric, fiscal_year)
        if row is None:
            year = f" for FY{fiscal_year}" if fiscal_year else ""
            notes.append(f"{COMPANIES[ticker]['name']} does not report {label.lower()}{year} "
                         "in its SEC XBRL data, so it is not included.")
        else:
            rows.append(row)

    rows.sort(key=lambda r: r["value"], reverse=True)
    summary = None
    if rows:
        top = rows[0]
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
            row["difference_vs_leader"] = row["value"] - top["value"]
            row["share_of_leader_pct"] = round(row["value"] / top["value"] * 100, 2) if top["value"] > 0 else None
    if len(rows) == 2:
        a, b = rows
        diff = a["value"] - b["value"]
        summary = (f"{a['company']}'s {label.lower()} ({a['value_display']}, FY{a['fiscal_year']}) is "
                   f"{format_money(diff)} higher than {b['company']}'s ({b['value_display']}, FY{b['fiscal_year']})")
        if b["value"] > 0:
            summary += f", or {(a['value'] / b['value'] - 1) * 100:.2f}% higher"
        summary += "."
    elif len(rows) > 2:
        summary = (f"Highest {label.lower()}: {rows[0]['company']} ({rows[0]['value_display']}, "
                   f"FY{rows[0]['fiscal_year']}). Lowest: {rows[-1]['company']} ({rows[-1]['value_display']}, "
                   f"FY{rows[-1]['fiscal_year']}).")

    if len({r["period_end"] for r in rows}) > 1:
        ends = ", ".join(f"{r['ticker']} {r['period_end']}" for r in rows)
        notes.append(f"Fiscal years end on different dates ({ends}). Each figure is that company's own "
                     "latest full fiscal year, not the same calendar period.")
    for r in rows:
        if r["derived"]:
            notes.append(f"{r['company']}'s {label.lower()} is derived by Python as total liabilities and "
                         "equity minus stockholders' equity, because the company does not report it directly.")
    return {"metric": metric, "label": label, "fiscal_year": fiscal_year,
            "rows": rows, "summary": summary, "notes": notes}


def figures_text(comparisons: list[dict]) -> str:
    """Comparison results as plain text for the LLM (numbers in several forms for the number guard)."""
    lines = []
    for comp in comparisons:
        lines.append(f"{comp['label']}:")
        for r in comp["rows"]:
            lines.append(f"- {r['company']} ({r['ticker']}): {r['value_display']} "
                         f"(USD {r['value']:,.0f}; ${r['value'] / 1e6:,.0f} million), FY{r['fiscal_year']}, "
                         f"period {r.get('period_start') or ''} to {r['period_end']}"
                         + (", derived" if r["derived"] else ""))
        if comp["summary"]:
            lines.append(f"Summary: {comp['summary']}")
        lines.extend(f"Note: {n}" for n in comp["notes"])
    return "\n".join(lines)
