"""Demo-day check: is everything ready? Run it before the interview.

python -m scripts.preflight          -> all local checks (no Gemini quota used)
python -m scripts.preflight --live   -> also asks Gemini for one tiny reply (1 request)

Exit code 0 = ready, 1 = something must be fixed.
"""
import argparse
import json
import time

import requests

from backend.config import (CACHE_DIR, GEMINI_API_KEY, METRICS_PATH, OLLAMA_ENABLED, OLLAMA_MODEL,
                            OLLAMA_URL, PROCESSED_DIR, SEC_COLLECTION, SEC_USER_AGENT)

results = []   # (ok: bool | None, name, detail)   None = warning only


def check(name: str, ok, detail: str = "") -> None:
    results.append((ok, name, detail))
    icon = {True: "PASS", False: "FAIL", None: "WARN"}[ok]
    print(f"[{icon}] {name}" + (f"  -  {detail}" if detail else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="also make 1 real Gemini request")
    args = parser.parse_args()

    key_ok = bool(GEMINI_API_KEY) and "your_" not in GEMINI_API_KEY
    check("Gemini API key in .env", key_ok, "set (not printed)" if key_ok else "missing or placeholder")
    ua_ok = bool(SEC_USER_AGENT) and "@" in SEC_USER_AGENT and "example.com" not in SEC_USER_AGENT
    check("SEC_USER_AGENT has a real email", ua_ok)

    reports = list(PROCESSED_DIR.glob("*_FY*.json"))
    check("10 processed 10-K reports", len(reports) == 10, f"{len(reports)} found")

    try:
        from backend.services.retrieval_service import get_or_create_collection
        chunks = get_or_create_collection(SEC_COLLECTION).count()
        check("SEC vector store", chunks > 0, f"{chunks:,} chunks")
    except Exception as exc:
        check("SEC vector store", False, str(exc))

    if METRICS_PATH.exists():
        import pandas as pd
        df = pd.read_csv(METRICS_PATH)
        latest = df[df["metric"] == "revenue"].groupby("ticker")["fiscal_year"].max().to_dict()
        check("Financial metrics (XBRL)", len(df) > 0, f"{len(df)} rows, latest FY: {latest}")
    else:
        check("Financial metrics (XBRL)", False, "run: python -m ingestion.fetch_financial_facts")

    start = time.time()
    try:
        from backend.services.embedding_service import embed_query
        embed_query("warm up")
        check("Embedding model loads offline", True, f"{time.time() - start:.1f} s")
    except Exception as exc:
        check("Embedding model loads offline", False, str(exc))

    if OLLAMA_ENABLED:
        try:
            tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
            names = [m["name"] for m in tags.get("models", [])]
            check("Ollama backup running", OLLAMA_MODEL in names, f"models: {names}")
        except requests.RequestException:
            check("Ollama backup running", None, "Ollama app not running (start it from the Start menu)")
    else:
        check("Ollama backup", None, "disabled in .env (OLLAMA_ENABLED=false)")

    cached = len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.exists() else 0
    check("Pre-warmed answers in cache", cached > 0 or None, f"{cached} saved answers (run scripts.prewarm)")

    for name, url in [("API server (port 8000)", "http://127.0.0.1:8000/health"),
                      ("UI server (port 8501)", "http://127.0.0.1:8501")]:
        try:
            ok = requests.get(url, timeout=3).status_code == 200
            check(name, ok)
        except requests.RequestException:
            check(name, None, "not running (start with run_demo.ps1)")

    if args.live:
        try:
            from backend.services.llm_service import generate_answer
            text, model = generate_answer("Reply with one word.", "Say OK.")
            check("Gemini answers (live)", True, f"{model}: {text[:30]!r}")
        except Exception as exc:
            check("Gemini answers (live)", False, str(exc)[:200])

    failed = [r for r in results if r[0] is False]
    warned = [r for r in results if r[0] is None]
    print(f"\n{len(results) - len(failed) - len(warned)} passed, {len(warned)} warnings, {len(failed)} failed")
    print("READY FOR THE DEMO" if not failed else "FIX THE FAILED ITEMS ABOVE")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
