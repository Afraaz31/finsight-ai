"""Pydantic schemas: the exact shape of every API request and response.

FastAPI uses these to (1) reject bad input with a clear 422 error, (2) build the /docs page,
and (3) guarantee the frontend always receives the same fields.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.companies import COMPANIES


# ---------- Level 13: guardrails ----------
class GuardrailResult(BaseModel):
    name: str                     # e.g. input_checks, pii_redaction, investment_advice
    action: str                   # passed | blocked | redacted | flagged | modified
    detail: str = ""


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
    text: str | None = None          # the full passage (Level 10)
    section_id: str | None = None    # e.g. "8" -> used by "Read the full section"
    deep_link: str | None = None     # opens the filing scrolled to this passage


class SectionResponse(BaseModel):
    """One full 10-K section (Level 10: read it inside FinSight, no SEC website needed)."""
    ticker: str
    company: str
    fiscal_year: int
    period_end: str
    section_id: str
    section: str
    text: str
    char_count: int
    document_url: str


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
    mode: Literal["compare", "trend"] = "compare"   # trend = one company, two years (Level 10)
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
    route: str = "narrative"                    # narrative | numbers | both | report  (Level 7, 11)
    financials: list[Comparison] | None = None  # exact SEC figures (Level 7)
    report: "CompanyReport | None" = None       # the 10-section Company Report (Level 11)
    guardrails: list[GuardrailResult] = []      # Level 13: what the guardrails checked / changed
    request_id: str | None = None               # Level 13: find this request on the Monitoring page


# ---------- Level 11: Company Report ----------
class ReportFact(BaseModel):
    label: str
    value: str
    note: str | None = None
    link: str | None = None


class ReportSection(BaseModel):
    id: str
    title: str
    facts: list[ReportFact] = []
    table: list[dict] | None = None
    text: str | None = None        # AI-written, with [n] citations (background, risks, outlook)
    note: str | None = None


class CompanyReport(BaseModel):
    ticker: str
    company: str
    fiscal_year: int
    period_end: str
    sections: list[ReportSection]
    skipped: list[str] = []        # sections with no data -> skipped, never guessed
    sources: list[SecSource] = []
    model: str | None = None
    used_llm: bool = False
    cached: bool = False
    unverified_numbers: list[str] = []
    markdown: str = ""
    guardrails: list[GuardrailResult] = []      # Level 13: what the guardrails checked / changed
    request_id: str | None = None               # Level 13: find this request on the Monitoring page


ChatResponse.model_rebuild()      # resolves the forward reference to CompanyReport


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
    text: str | None = None       # the full passage (Level 10)
    score: float | None = None
    ref: str | None = None        # spreadsheet results: "T1", "T2" (Level 12)


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
    guardrails: list[GuardrailResult] = []      # Level 13: what the guardrails checked / changed
    request_id: str | None = None               # Level 13: find this request on the Monitoring page


# ---------- Level 12: Orchestrator + 2 agents ----------
class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000,
                          examples=["Does the revenue in the spreadsheet match the annual report?"])
    doc_ids: list[str] = Field(default=[], max_length=10)   # empty -> the Orchestrator looks at all uploads
    sheet: str | None = None
    use_cache: bool = True


class AgentStep(BaseModel):
    agent: str                    # "Spreadsheet Agent" | "Document Agent"
    task: str                     # what the Orchestrator asked it to do
    files: list[str]
    status: str                   # "done" or what went wrong


class OrchestratorTrace(BaseModel):
    decided_by: str               # "ai" (Gemini planner) | "rules" (fallback / only one file type)
    reason: str
    agents: list[AgentStep]


class TableCalculation(BaseModel):
    ref: str
    filename: str
    sheet: str
    plan: dict
    summary: str
    table: list[dict] | None = None


class AssistantAnswer(BaseModel):
    answer: str
    sources: list[UploadSource]
    documents: list[str]
    used_llm: bool
    model: str | None = None
    cached: bool = False
    calculation: TableCalculation | None = None
    calculations: list[TableCalculation] = []
    unverified_numbers: list[str] = []
    orchestrator: OrchestratorTrace
    guardrails: list[GuardrailResult] = []      # Level 13: what the guardrails checked / changed
    request_id: str | None = None               # Level 13: find this request on the Monitoring page
