"""Live demo on Streamlit Community Cloud: run the FastAPI backend INSIDE the Streamlit process.

Streamlit Cloud runs one program (`streamlit run frontend/app.py`), so there the API runs in a background
thread on 127.0.0.1:8000 and the UI talks to it exactly as it does locally. This only happens when
deploy_meta.json exists (it is written by `python -m scripts.deploy_space build-streamlit`); a normal
local run never starts anything here.
"""
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_META = ROOT / "deploy_meta.json"
HEALTH_URL = "http://127.0.0.1:8000/health"


def deploy_settings() -> dict | None:
    """The live demo's settings, or None when running locally."""
    if not DEPLOY_META.exists():
        return None
    return json.loads(DEPLOY_META.read_text(encoding="utf-8"))


def apply_settings(meta: dict) -> None:
    """Public-demo settings (never secrets: the Gemini key comes from Streamlit's Secrets box)."""
    for key, value in meta.get("env", {}).items():
        os.environ.setdefault(key, str(value))
    # Saved answers are keyed on the SEC figures file's timestamp; git checkouts reset it, so restore it.
    metrics = ROOT / "data" / "financial" / "metrics.csv"
    if metrics.exists() and "metrics_mtime_ns" in meta:
        os.utime(metrics, ns=(meta["metrics_mtime_ns"], meta["metrics_mtime_ns"]))


def api_is_up() -> bool:
    try:
        urllib.request.urlopen(HEALTH_URL, timeout=2)
        return True
    except Exception:
        return False


def start_api(timeout: float = 240) -> bool:
    """Start uvicorn in a daemon thread (once per process) and wait until /health answers."""
    if api_is_up():
        return True
    import uvicorn

    from backend.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning"))
    threading.Thread(target=server.run, name="finsight-api", daemon=True).start()
    end = time.time() + timeout
    while time.time() < end:
        if api_is_up():
            return True
        time.sleep(0.5)
    return False
