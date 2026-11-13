"""Level 11: the 10-section Company Report for one company."""
from fastapi import APIRouter, Path, Query

from backend import guardrails
from backend import observability as obs
from backend.routes import _guarded

from backend.schemas.api_schemas import CompanyReport
from backend.services.report_service import build_report

router = APIRouter(tags=["reports"])


@router.get("/report/{ticker}", response_model=CompanyReport)
def company_report(ticker: str = Path(examples=["AAPL"]),
                   fiscal_year: int | None = Query(None, examples=[2026]),
                   use_cache: bool = True) -> dict:
    """Overview, background, financials, balance sheet, income statement, ratios, performance,
    risks, outlook and sources. Sections without data are skipped and listed in `skipped`."""
    obs.set_field("question", f"Company report {ticker.upper()}" + (f" FY{fiscal_year}" if fiscal_year else ""))
    report = guardrails.check_report(build_report(ticker, fiscal_year, use_cache=use_cache))
    return _guarded.after({**report, "route": "report"})
