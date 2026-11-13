"""Level 13: Monitoring - observability and guardrails at a glance (reads GET /observability/*)."""
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from frontend import api_client, ui
from frontend.api_client import ApiError

ui.page_header(ui.finsight_mark(44), "Monitoring",
               "Observability and guardrails: every request is traced (latency, AI calls, tokens, cache, "
               "guardrail actions), so you can see what the system did and why.")

top = st.columns([1, 1, 4])
limit = top[0].selectbox("Recent requests", [25, 50, 100, 200], index=1)
top[1].markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
if top[1].button("↻ Refresh", width="stretch"):
    st.rerun()

try:
    summary = api_client.observability_summary()
    traces = api_client.observability_traces(limit)
except ApiError as exc:
    st.error(exc.message)
    st.stop()


def kpi(col, value, label: str, sub: str = "") -> None:
    col.markdown(f"<div class='fs-card fs-kpi'><div class='v'>{value}</div><div class='l'>{label}</div>"
                 f"<div class='fs-muted' style='font-size:.75rem'>{sub}</div></div>", unsafe_allow_html=True)


def local(ts: str) -> datetime:
    """Traces are stored in UTC; show them in this computer's time zone (e.g. IST)."""
    return datetime.fromisoformat(ts).astimezone().replace(tzinfo=None)


def ms(value) -> str:
    return "—" if value is None else (f"{value / 1000:.1f} s" if value >= 1000 else f"{value:.0f} ms")


# ---------- KPI cards ----------
k = st.columns(4)
kpi(k[0], summary["requests"], "Questions answered", f"{summary['errors']} server errors")
kpi(k[1], ms(summary["p50_latency_ms"]), "Median latency", f"p95 {ms(summary['p95_latency_ms'])}")
kpi(k[2], "—" if summary["cache_hit_rate_pct"] is None else f"{summary['cache_hit_rate_pct']:.0f}%",
    "Cache hit rate", "saved answers use no quota")
used, limit_day = summary["llm_calls_today"], summary["daily_llm_call_limit"]
kpi(k[3], f"{used} / {limit_day}", "Gemini calls today", "daily budget guardrail")
k = st.columns(4)
kpi(k[0], summary["llm_calls"], "AI calls (all)", f"{summary['llm_failures']} failed · {summary['fallbacks']} fallbacks")
kpi(k[1], f"{summary['prompt_tokens'] + summary['output_tokens']:,}", "Tokens",
    f"{summary['prompt_tokens']:,} in · {summary['output_tokens']:,} out")
kpi(k[2], summary["blocked"], "Requests blocked", "by input guardrails / rate limit")
kpi(k[3], summary["unverified_number_answers"], "Answers with flagged numbers", "number guard")
st.progress(min(used / limit_day, 1.0) if limit_day else 0.0,
            text=f"Free-tier budget used today: {used} of {limit_day} Gemini calls")

# ---------- charts ----------
left, right = st.columns(2)
with left:
    st.markdown("**Latency per request**")
    rows = [{"time": local(t["ts"]), "latency (s)": (t.get("latency_ms") or 0) / 1000, "endpoint": t["endpoint"]}
            for t in traces if t.get("latency_ms") is not None]
    if rows:
        st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_circle(size=60).encode(
            x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M")), y="latency (s):Q", color="endpoint:N",
            tooltip=[alt.Tooltip("time:T", format="%H:%M:%S"), "endpoint", "latency (s):Q"]).properties(height=240), width="stretch")
    else:
        st.caption("No requests yet. Ask a question, then refresh.")
with right:
    st.markdown("**AI calls per model**")
    models = [{"model": m, "calls": v["calls"], "failed": v["failed"],
               "avg latency": ms(v["avg_latency_ms"]), "tokens": v["prompt_tokens"] + v["output_tokens"]}
              for m, v in summary["by_model"].items()]
    if models:
        st.altair_chart(alt.Chart(pd.DataFrame(models)).mark_bar().encode(
            x=alt.X("calls:Q"), y=alt.Y("model:N", sort="-x", title=None),
            tooltip=["model", "calls", "failed", "avg latency", "tokens"]).properties(height=240),
            width="stretch")
    else:
        st.caption("No AI calls yet.")

g1, g2 = st.columns(2)
with g1:
    st.markdown("**🛡️ Guardrail actions**")
    if summary["guardrails"]:
        st.dataframe(pd.DataFrame([{"guardrail": k.split(":")[0].replace("_", " "), "action": k.split(":")[1],
                                    "count": v} for k, v in summary["guardrails"].items()]),
                     hide_index=True, width="stretch")
    else:
        st.caption("No guardrail has blocked, redacted or flagged anything yet.")
with g2:
    st.markdown("**Questions by route**")
    if summary["by_route"]:
        st.dataframe(pd.DataFrame([{"route": k, "requests": v} for k, v in summary["by_route"].items()]),
                     hide_index=True, width="stretch")
    else:
        st.caption("No questions yet.")

# ---------- recent requests ----------
st.markdown("### Recent requests")
table = [{"time": local(t["ts"]).strftime("%H:%M:%S"), "request id": t["request_id"], "endpoint": t["endpoint"],
          "status": t["status"], "latency": ms(t.get("latency_ms")), "route": t.get("route") or "—",
          "AI calls": len(t.get("llm_calls", [])), "cached": {True: "yes", False: "no"}.get(t.get("cached"), "—"),
          "guardrails": ", ".join(f"{g['name']}:{g['action']}" for g in t.get("guardrails", [])
                                  if g["action"] != "passed") or "ok",
          "question": t.get("question") or ""} for t in traces]
if api_client.PUBLIC_DEMO:      # the API already removes them; drop the empty column too
    table = [{k: v for k, v in row.items() if k != "question"} for row in table]
    st.caption("🔒 Public demo: visitors' questions are not shown. Everything else is the live trace data.")
if table:
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    pick = st.selectbox("Inspect one request (its full trace)", [t["request_id"] for t in traces],
                        format_func=lambda rid: next(f"{x['time']} · {x['endpoint']} · {x.get('question', '')[:60]}"
                                                     for x in table if x["request id"] == rid))
    trace = next(t for t in traces if t["request_id"] == pick)
    a, b = st.columns(2)
    with a:
        st.markdown("**Steps (spans)**")
        st.dataframe(pd.DataFrame(trace.get("spans") or [{"name": "—", "ms": None}]), hide_index=True,
                     width="stretch")
        st.markdown("**AI calls**")
        st.dataframe(pd.DataFrame(trace.get("llm_calls") or [{"model": "none"}]), hide_index=True, width="stretch")
    with b:
        st.markdown("**Guardrails**")
        st.dataframe(pd.DataFrame(trace.get("guardrails") or [{"name": "—"}]), hide_index=True, width="stretch")
        with st.expander("Raw trace (JSON)"):
            st.json(trace)
else:
    st.info("No requests recorded yet.")
