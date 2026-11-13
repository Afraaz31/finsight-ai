"""Level 13: observability. For every API request we can answer: what happened, how long it took,
which AI models were called (and how many tokens), what was blocked, and what failed.

    request ──► middleware starts a TRACE (request id, endpoint, start time)
                  ├─ route / events       route chosen, chunks retrieved, cache hit ...
                  ├─ span("retrieve")     how long the vector search took (also each agent, the report)
                  ├─ llm call             model, latency, tokens, ok / error / fallback
                  └─ guardrail records    what was blocked, redacted or flagged
              ◄── middleware finishes it: status code, total latency → one JSON line in traces.jsonl

The current trace lives in a ContextVar, so any code (llm_service, agents, ...) can add to it
without passing it around. Storage is a local JSON-lines file: free, simple, easy to inspect.
"""
import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock

from backend.config import OBS_DIR

log = logging.getLogger("finsight.obs")
TRACES_FILE = OBS_DIR / "traces.jsonl"
_current: ContextVar[dict | None] = ContextVar("finsight_trace", default=None)
_lock = Lock()


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------- trace lifecycle (called by the middleware) ----------
def start_trace(request_id: str, method: str, path: str) -> dict:
    trace = {"request_id": request_id, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "method": method, "endpoint": path, "status": None, "latency_ms": None, "question": None,
             "route": None, "cached": None, "spans": [], "llm_calls": [], "guardrails": [], "events": [],
             "error": None, "_t0": time.perf_counter()}
    _current.set(trace)
    return trace


def finish_trace(status: int, error: str | None = None) -> dict | None:
    trace = _current.get()
    if trace is None:
        return None
    trace["status"] = status
    trace["latency_ms"] = round((time.perf_counter() - trace.pop("_t0")) * 1000, 1)
    trace["error"] = error or trace["error"]
    _current.set(None)
    _write(trace)
    return trace


def _write(trace: dict) -> None:
    try:
        OBS_DIR.mkdir(parents=True, exist_ok=True)
        with _lock, TRACES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:            # observability must never break the app
        log.warning("Could not write trace: %s", exc)


# ---------- adding information (called from anywhere) ----------
def current() -> dict | None:
    return _current.get()


def set_field(key: str, value) -> None:
    if (t := _current.get()) is not None:
        t[key] = value


def event(name: str, **data) -> None:
    if (t := _current.get()) is not None:
        t["events"].append({"name": name, **data})


@contextmanager
def span(name: str, **data):
    """with span("retrieve", companies="AAPL"): ...   -> records how long the block took."""
    t0 = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        if (t := _current.get()) is not None:
            t["spans"].append({"name": name, "ms": round((time.perf_counter() - t0) * 1000, 1),
                               "status": status, **data})


def record_llm_call(model: str, ok: bool, latency_ms: float, prompt_tokens: int | None = None,
                    output_tokens: int | None = None, error: str | None = None, purpose: str | None = None) -> None:
    entry = {"model": model, "ok": ok, "latency_ms": round(latency_ms, 1), "prompt_tokens": prompt_tokens,
             "output_tokens": output_tokens, "error": error, "purpose": purpose,
             "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if (t := _current.get()) is not None:
        t["llm_calls"].append(entry)
    else:                               # e.g. called from a script (prewarm): still counted for the daily budget
        _write({"request_id": None, "ts": entry["ts"], "endpoint": "(script)", "status": 200, "latency_ms": 0,
                "spans": [], "llm_calls": [entry], "guardrails": [], "events": []})
    log.info("LLM %s %s %.0f ms tokens=%s/%s %s", model, "ok" if ok else "FAILED", latency_ms,
             prompt_tokens, output_tokens, error or "")


def record_guardrail(name: str, action: str, detail: str = "") -> None:
    """action: passed | blocked | redacted | flagged | modified"""
    if (t := _current.get()) is not None:
        t["guardrails"].append({"name": name, "action": action, "detail": detail})


def guardrail_report() -> list[dict]:
    t = _current.get()
    return list(t["guardrails"]) if t else []


# ---------- reading (for /observability and the daily budget) ----------
def load_traces(limit: int = 2000) -> list[dict]:
    if not TRACES_FILE.exists():
        return []
    try:
        lines = TRACES_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError as exc:
        log.warning("Could not read traces: %s", exc)
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _is_gemini_ok(call: dict) -> bool:
    return bool(call.get("ok")) and not str(call.get("model", "")).startswith("ollama")


def llm_calls_today() -> int:
    """Successful Gemini calls since midnight UTC (Gemini's free quota resets at midnight Pacific;
    UTC is a slightly stricter, simpler approximation)."""
    today = datetime.now(timezone.utc).date().isoformat()
    count = sum(1 for t in load_traces(20000) for c in t.get("llm_calls", [])
                if _is_gemini_ok(c) and str(c.get("ts", "")).startswith(today))
    t = _current.get()
    if t:   # calls in the request that is still running are not on disk yet
        count += sum(1 for c in t["llm_calls"] if _is_gemini_ok(c))
    return count


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))], 1)


def is_question(trace: dict) -> bool:
    """Requests that answer something (may call the AI), as opposed to page loads like GET /companies."""
    return (trace.get("method") == "POST" and trace.get("endpoint") != "/uploads") \
        or str(trace.get("endpoint", "")).startswith("/report")


def summary(limit: int = 2000) -> dict:
    """Numbers for the Monitoring page. Only question-answering endpoints count as "requests"."""
    traces = [t for t in load_traces(limit) if is_question(t)]
    lat = [t["latency_ms"] for t in traces if t.get("latency_ms") is not None]
    calls = [c for t in traces for c in t.get("llm_calls", [])]
    by_model, by_route, guards = {}, {}, {}
    for c in calls:
        m = by_model.setdefault(c["model"], {"calls": 0, "failed": 0, "prompt_tokens": 0, "output_tokens": 0,
                                             "latency": []})
        m["calls"] += 1
        m["failed"] += 0 if c.get("ok") else 1
        m["prompt_tokens"] += c.get("prompt_tokens") or 0
        m["output_tokens"] += c.get("output_tokens") or 0
        m["latency"].append(c.get("latency_ms") or 0)
    for m in by_model.values():
        m["avg_latency_ms"] = round(sum(m["latency"]) / len(m["latency"]), 1) if m["latency"] else None
        del m["latency"]
    for t in traces:
        by_route[t.get("route") or "other"] = by_route.get(t.get("route") or "other", 0) + 1
        for g in t.get("guardrails", []):
            if g["action"] != "passed":
                key = f"{g['name']}:{g['action']}"
                guards[key] = guards.get(key, 0) + 1
    answered = [t for t in traces if t.get("cached") is not None]
    return {
        "requests": len(traces),
        "errors": sum(1 for t in traces if (t.get("status") or 0) >= 500),
        "blocked": sum(1 for t in traces if any(g["action"] == "blocked" for g in t.get("guardrails", []))),
        "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else None,
        "p50_latency_ms": _pct(lat, 50), "p95_latency_ms": _pct(lat, 95),
        "cache_hit_rate_pct": round(100 * sum(1 for t in answered if t["cached"]) / len(answered), 1)
        if answered else None,
        "llm_calls": len(calls), "llm_failures": sum(1 for c in calls if not c.get("ok")),
        "fallbacks": sum(1 for t in traces if len({c["model"] for c in t.get("llm_calls", [])}) > 1
                         and any(not c.get("ok") for c in t.get("llm_calls", []))),
        "llm_calls_today": llm_calls_today(),
        "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in calls),
        "output_tokens": sum(c.get("output_tokens") or 0 for c in calls),
        "by_model": by_model, "by_route": by_route, "guardrails": guards,
        "unverified_number_answers": sum(1 for t in traces if any(e["name"] == "number_guard" and e.get("flagged")
                                                                  for e in t.get("events", []))),
    }
