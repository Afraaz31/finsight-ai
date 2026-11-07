"""Pydantic schemas: the exact shape of every API request and response.

FastAPI uses these to (1) reject bad input with a clear 422 error, (2) build the /docs page,
and (3) guarantee the frontend always receives the same fields.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.companies import COMPANIES


# ---------- health & companies ----------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    sec_chunks: int
    uploads: int
    llm_model: str
    fallback_models: list[str]
    ollama_enabled: bool
    api_key_configured: bool
    problems: list[str] = []


class Company(BaseModel):
    ticker: str
    name: str
    cik: str
    fiscal_years: list[int]


# ---------- SEC chat ----------
class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, examples=["What are NVIDIA's major business risks?"])
    ticker: str | None = Field(default=None, description="Optional: force one company, e.g. AAPL")
    use_cache: bool = True

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Question is too short.")
        return value

    @field_validator("ticker")
    @classmethod
    def supported_ticker(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        value = value.strip().upper()
        if value not in COMPANIES:
            raise ValueError(f"Unsupported ticker '{value}'. Supported: {', '.join(COMPANIES)}")
        return value


class SecSource(BaseModel):
    number: int
    company: str
    ticker: str
    fiscal_year: int
    period_end: str
    section: str
    document_url: str
    score: float
    excerpt: str


# ---------- financial figures (Level 7) ----------
class FinancialRow(BaseModel):
    ticker: str
    company: str
    metric: str
    label: str
    fiscal_year: int
    period_start: str | None = None
    period_end: str
    value: float
    value_display: str
    unit: str
    tag: str
    derived: bool
    form: str
    accession: str
    filed: str
    source_url: str
    rank: int | None = None
    difference_vs_leader: float | None = None
    share_of_leader_pct: float | None = None
    yoy_change: float | None = None
    yoy_change_pct: float | None = None


class Comparison(BaseModel):
    metric: str
    label: str
    fiscal_year: int | None = None
    rows: list[FinancialRow]
    summary: str | None = None
    notes: list[str] = []


class CompareRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=5, examples=[["AAPL", "MSFT"]])
    metric: str = Field(examples=["revenue"])
    fiscal_year: int | None = Field(default=None, description="Leave empty for each company's latest year")

    @field_validator("tickers")
    @classmethod
    def supported_tickers(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip().upper() for t in value]
        unknown = [t for t in cleaned if t not in COMPANIES]
        if unknown:
            raise ValueError(f"Unsupported ticker(s) {unknown}. Supported: {', '.join(COMPANIES)}")
        return cleaned

    @field_validator("metric")
    @classmethod
    def known_metric(cls, value: str) -> str:
        from backend.services.financial_service import METRICS
        value = value.strip().lower()
        if value not in METRICS:
            raise ValueError(f"Unknown metric '{value}'. Available: {', '.join(METRICS)}")
        return value


class MetricHistory(BaseModel):
    metric: str
    label: str
    latest: FinancialRow | None = None
    history: list[FinancialRow]


class CompanyFinancials(BaseModel):
    ticker: str
    company: str
    metrics: list[MetricHistory]


class ChatResponse(BaseModel):
    answer: str
    sources: list[SecSource]
    companies: list[str]
    used_llm: bool
    model: str | None = None
    cached: bool = False
    retrieved_chunks: int = 0
    unverified_numbers: list[str] = []
    route: str = "narrative"                    # narrative | numbers | both  (Level 7)
    financials: list[Comparison] | None = None  # exact SEC figures (Level 7)


# ---------- uploads ----------
class UploadTable(BaseModel):
    sheet: str
    file: str
    rows: int
    columns: list[str]
    reshaped_to_long: bool


class UploadMeta(BaseModel):
    doc_id: str
    filename: str
    extension: str
    size_bytes: int
    uploaded_at: str
    kind: Literal["text", "table"]
    pages: int | None = None
    characters: int | None = None
    chunks: int | None = None
    tables: list[UploadTable] | None = None


class UploadAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, examples=["What is the net profit margin for each year?"])
    doc_ids: list[str] = Field(min_length=1, max_length=5)
    sheet: str | None = None
    use_cache: bool = True


class UploadSource(BaseModel):
    filename: str
    number: int | None = None     # text documents: citation number [n]
    page: int | None = None       # text documents
    sheet: str | None = None      # tables
    detail: str | None = None     # tables: what Python calculated
    excerpt: str | None = None
    score: float | None = None


class Calculation(BaseModel):
    plan: dict
    summary: str
    table: list[dict] | None = None


class UploadAnswer(BaseModel):
    answer: str
    sources: list[UploadSource]
    documents: list[str]
    used_llm: bool
    model: str | None = None
    cached: bool = False
    calculation: Calculation | None = None
    unverified_numbers: list[str] = []
