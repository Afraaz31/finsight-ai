"""One place that reads settings from the .env file."""
import os

from dotenv import load_dotenv

# Find the .env file and load its lines into environment variables.
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
