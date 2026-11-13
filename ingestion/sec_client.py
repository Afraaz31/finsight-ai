"""Polite, cached access to SEC EDGAR. Every SEC request in the project goes through here."""
import json
import logging
import time
from pathlib import Path

import requests

from backend.config import SEC_USER_AGENT, require

log = logging.getLogger(__name__)

MIN_SECONDS_BETWEEN_REQUESTS = 0.2  # max 5 requests/second (SEC's limit is 10)
MAX_RETRIES = 3
TIMEOUT_SECONDS = 60
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_session = None
_last_request_at = 0.0


class SECRequestError(Exception):
    """Raised when SEC data can't be fetched."""


def _get_session() -> requests.Session:
    """One shared session: reuses the connection and always sends our User-Agent."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = require("SEC_USER_AGENT", SEC_USER_AGENT)
    return _session


def _wait_for_rate_limit() -> None:
    """Sleep just long enough to keep requests at least 0.2 s apart."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
        time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
    _last_request_at = time.monotonic()


def fetch(url: str) -> bytes:
    """Download a URL from SEC with rate limiting and retries. Returns raw bytes."""
    session = _get_session()
    for attempt in range(1, MAX_RETRIES + 1):
        _wait_for_rate_limit()
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as exc:
            log.warning("Network problem on %s (attempt %d/%d): %s", url, attempt, MAX_RETRIES, exc)
        else:
            if response.status_code == 200:
                return response.content
            if response.status_code not in RETRYABLE_STATUS:
                # 403 = missing/bad User-Agent, 404 = wrong URL. Retrying won't help.
                raise SECRequestError(f"SEC returned {response.status_code} for {url}")
            log.warning("SEC returned %d for %s (attempt %d/%d)",
                        response.status_code, url, attempt, MAX_RETRIES)
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)  # back off: 2 s, then 4 s
    raise SECRequestError(f"Gave up on {url} after {MAX_RETRIES} attempts")


def fetch_to_file(url: str, path: Path, max_age_hours: float | None = None) -> Path:
    """Download url to path, unless a usable cached copy already exists.

    max_age_hours=None means "never expires" (good for 10-K documents, which never change).
    """
    if path.exists() and path.stat().st_size > 0:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if max_age_hours is None or age_hours < max_age_hours:
            log.info("Cached     %s", path.name)
            return path

    path.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url)
    temp_path = path.with_name(path.name + ".part")
    temp_path.write_bytes(data)
    temp_path.replace(path)  # rename only after the full download succeeded
    log.info("Downloaded %s (%.1f MB)", path.name, len(data) / 1_000_000)
    return path


def fetch_json(url: str, path: Path, max_age_hours: float | None = 24) -> dict:
    """Cached download of a JSON endpoint, returned as a Python dict."""
    fetch_to_file(url, path, max_age_hours)
    return json.loads(path.read_text(encoding="utf-8"))
