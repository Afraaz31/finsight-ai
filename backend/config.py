"""One place that reads settings from the .env file."""
import os

from dotenv import load_dotenv

# Find the .env file and load its lines into environment variables.
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")


def require(name: str, value: str | None) -> str:
    """Stop early with a clear message if a setting is missing or still a placeholder."""
    if not value or "your_" in value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill in a real value."
        )
    return value


# ---------- Project paths (Level 1) ----------
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # downloaded originals (HTML, JSON)
PROCESSED_DIR = DATA_DIR / "processed"  # cleaned text, split into sections
FINANCIAL_DIR = DATA_DIR / "financial"  # Level 4: structured numbers
VECTORSTORE_DIR = PROJECT_ROOT / "vectorstore"  # Level 2: ChromaDB

# ---------- RAG settings (Level 2) ----------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = 800          # max characters per chunk (model reads ~256 tokens ≈ 1,000 chars)
CHUNK_OVERLAP = 150       # characters repeated between neighbouring chunks
SEC_COLLECTION = "sec_filings"      # ChromaDB collection for the 5 companies' 10-Ks
UPLOAD_COLLECTION = "user_uploads"  # Level 4: user-uploaded documents (kept separate)

# ---------- Answer generation settings (Level 3) ----------
RAG_TOP_K = 5                 # chunks retrieved per company for a question
MAX_CONTEXT_CHUNKS = 15       # hard cap on chunks sent to Gemini (protects the free quota)
MIN_RELEVANCE_SCORE = 0.25    # chunks scoring below this are treated as "not relevant"
LLM_TEMPERATURE = 0.2         # low = factual and consistent, high = creative

# ---------- Quota Shield (Level 3.5) ----------
# Tried in order after GEMINI_MODEL fails (quota, overload, missing model). Each has its own free quota.
GEMINI_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemma-4-31b-it").split(",")
    if m.strip()
]
LLM_TIMEOUT_SECONDS = 120                     # a stuck request gives up after this
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "false").lower() == "true"   # last-resort local model
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = 300                  # CPU-only laptops are slow
CACHE_DIR = DATA_DIR / "cache" / "answers"    # saved answers (data/ is gitignored)

# ---------- Uploaded documents (Level 4) ----------
UPLOAD_DIR = DATA_DIR / "uploads"            # one folder per uploaded file (gitignored)
MAX_UPLOAD_MB = 10
TEXT_EXTENSIONS = {".pdf", ".txt", ".docx"}  # -> RAG (chunks + embeddings)
TABLE_EXTENSIONS = {".csv", ".xlsx"}         # -> Pandas (exact calculations)
SMALL_DOC_CHUNKS = 8                         # docs this small: send ALL chunks (good for summaries)

# ---------- Structured financial data (Level 7) ----------
METRICS_PATH = FINANCIAL_DIR / "metrics.csv"   # one row per company x metric x fiscal year
FINANCIAL_YEARS_KEPT = 5                        # most recent fiscal years kept per metric

# ---------- Level 13: observability + guardrails ----------
OBS_DIR = DATA_DIR / "observability"          # traces.jsonl: one line per API request (gitignored)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))     # questions per client per minute
DAILY_LLM_CALL_LIMIT = int(os.getenv("DAILY_LLM_CALL_LIMIT", "400"))     # stop before the free quota (500/day)
