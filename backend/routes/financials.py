"""Level 7: exact financial figures from SEC XBRL data (no LLM involved in these endpoints)."""
from fastapi import APIRouter

from backend.schemas.api_schemas import CompanyFinancials, Comparison, CompareRequest
from backend.services.financial_service import METRICS, company_financials, compare

router = APIRouter(tags=["financials"])


@router.get("/metrics")
def metrics() -> list[dict]:
    """The financial metrics FinSight can retrieve and compare."""
    return [{"metric": key, "label": spec["label"], "period_type": spec["type"]}
            for key, spec in METRICS.items()]


@router.get("/financials/{ticker}", response_model=CompanyFinancials)
def financials(ticker: str) -> dict:
    """All metrics for one company: latest value and up to 5 years of history (with YoY change)."""
    return company_financials(ticker)


@router.post("/compare", response_model=Comparison)
def compare_companies(request: CompareRequest) -> dict:
    """Compare one metric across 2-5 companies: ranking, difference, % difference, period notes."""
    return compare(request.tickers, request.metric, request.fiscal_year)
