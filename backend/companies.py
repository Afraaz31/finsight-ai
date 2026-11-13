"""The companies FinSight AI supports. Change companies here and nowhere else."""

COMPANIES = {
    "AAPL": {"name": "Apple Inc.", "cik": "0000320193"},
    "MSFT": {"name": "Microsoft Corporation", "cik": "0000789019"},
    "AMZN": {"name": "Amazon.com, Inc.", "cik": "0001018724"},
    "GOOGL": {"name": "Alphabet Inc.", "cik": "0001652044"},
    "NVDA": {"name": "NVIDIA Corporation", "cik": "0001045810"},
}


def get_company(ticker: str) -> dict:
    """Return {'ticker', 'name', 'cik'} for a supported ticker, or raise ValueError."""
    t = ticker.upper().strip()
    if t not in COMPANIES:
        raise ValueError(f"Unsupported ticker '{ticker}'. Supported: {', '.join(COMPANIES)}")
    return {"ticker": t, **COMPANIES[t]}


# ---------- Level 3: words that mean each company in a question ----------
COMPANY_ALIASES = {
    "AAPL": ["apple", "aapl", "iphone"],
    "MSFT": ["microsoft", "msft", "azure"],
    "AMZN": ["amazon", "amzn", "aws"],
    "GOOGL": ["alphabet", "google", "googl", "youtube"],
    "NVDA": ["nvidia", "nvda"],
}
