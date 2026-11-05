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
