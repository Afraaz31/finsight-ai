"""Level 11: the 10-section Company Report for one company."""
from fastapi import APIRouter, Path, Query

from backend.schemas.api_schemas import CompanyReport
from backend.services.report_service import build_report

router = APIRouter(tags=["reports"])


@router.get("/report/{ticker}", response_model=CompanyReport)
def company_report(ticker: str = Path(examples=["AAPL"]),
                   fiscal_year: int | None = Query(None, examples=[2026]),
                   use_cache: bool = True) -> dict:
    """Overview, background, financials, balance sheet, income statement, ratios, performance,
    risks, outlook and sources. Sections without data are skipped and listed in `skipped`."""
    return build_report(ticker, fiscal_year, use_cache=use_cache)
