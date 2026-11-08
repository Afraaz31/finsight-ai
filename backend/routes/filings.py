"""Level 10: read a full 10-K section inside FinSight (no need to open the SEC website)."""
from fastapi import APIRouter, Query

from backend.schemas.api_schemas import SectionResponse
from backend.services.filing_service import get_section, list_sections

router = APIRouter(prefix="/sec", tags=["filings"])


@router.get("/sections")
def sections(ticker: str = Query(examples=["AAPL"]), fiscal_year: int = Query(examples=[2026])) -> list[dict]:
    """The sections available in one processed 10-K (Item 1, 1A, 7, 7A, 8, 9A ...)."""
    return list_sections(ticker, fiscal_year)


@router.get("/section", response_model=SectionResponse)
def section(ticker: str = Query(examples=["AAPL"]), fiscal_year: int = Query(examples=[2026]),
            section_id: str = Query(examples=["8"])) -> dict:
    """The full text of one 10-K section, e.g. Item 8 (Financial Statements, with the auditor's report)."""
    return get_section(ticker, fiscal_year, section_id)
