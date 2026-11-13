"""Answer cache: the same question gets the saved answer instantly, with no LLM call.

Each answer is one small JSON file in data/cache/answers/. Delete that folder to clear the cache.
"""
import hashlib
import json
import logging
import re
import time

from backend.config import CACHE_DIR

log = logging.getLogger(__name__)


def normalize(question: str) -> str:
    """'  What are Apple's RISKS?? ' and 'what are apple's risks' count as the same question."""
    q = re.sub(r"\s+", " ", question.lower()).strip()
    return q.rstrip("?!. ")


def make_key(*parts) -> str:
    """Stable file name from the question plus anything else that changes the answer."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def get(key: str) -> dict | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["result"]
    except (json.JSONDecodeError, KeyError):
        log.warning("Ignoring broken cache file %s", path.name)
        return None


def put(key: str, question: str, result: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"question": question, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "result": result}
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
