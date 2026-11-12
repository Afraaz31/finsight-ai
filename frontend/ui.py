"""Shared look and building blocks for every FinSight page: theme CSS, cards, answers, sources.

Pages import this module, so the design lives in ONE place.
"""
import html
import json
import re

import pandas as pd
import streamlit as st

from frontend import api_client
from frontend.api_client import ApiError
from frontend.logos import BRAND_COLORS, company_logo, company_logo_img, finsight_mark

TICKERS = ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root {--fs-bg:#060A14; --fs-panel:rgba(255,255,255,.035); --fs-line:rgba(148,163,184,.14); --fs-text:#EEF2FA;
  --fs-mute:#8B9AB4; --fs-blue:#3B82F6; --fs-cyan:#22D3EE; --fs-violet:#8B5CF6;}
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea {font-family: 'Inter', 'Segoe UI', sans-serif;}
.stApp {background:
  radial-gradient(900px 520px at 12% -8%, rgba(59,130,246,.20), transparent 60%),
  radial-gradient(800px 500px at 95% 4%, rgba(139,92,246,.16), transparent 60%),
  radial-gradient(700px 600px at 60% 110%, rgba(34,211,238,.08), transparent 60%), var(--fs-bg);
  background-attachment: fixed;}
[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px;}

/* sidebar */
[data-testid="stSidebar"] {background: linear-gradient(180deg,#0B1222 0%,#070C18 100%); border-right: 1px solid var(--fs-line);}
[data-testid="stSidebarNav"] a {border-radius: 12px; margin: 3px 8px; padding: 7px 12px; transition: background .15s;}
[data-testid="stSidebarNav"] a:hover {background: rgba(255,255,255,.04);}
[data-testid="stSidebarNav"] a[aria-current="page"] {background: linear-gradient(90deg,rgba(59,130,246,.22),rgba(139,92,246,.10));
  box-shadow: inset 3px 0 0 var(--fs-blue);}
[data-testid="stSidebarNav"] a[aria-current="page"] span {color: #FFFFFF; font-weight: 700;}

h1, h2, h3 {letter-spacing: -0.02em; color: var(--fs-text);}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 18px;}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
  background: var(--fs-panel); border-color: var(--fs-line) !important;}

/* buttons */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {border-radius: 12px; font-weight: 600;
  border: 1px solid rgba(148,163,184,.22); background: rgba(255,255,255,.03); color: var(--fs-text);
  transition: all .18s ease;}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover {border-color: rgba(96,165,250,.7);
  background: rgba(59,130,246,.10); color: #FFFFFF; box-shadow: 0 0 0 3px rgba(59,130,246,.12);}
.stButton > button[kind="primary"] {background: linear-gradient(135deg,#2563EB 0%,#4F46E5 55%,#7C3AED 100%); border: none;
  color: #fff; box-shadow: 0 8px 24px rgba(79,70,229,.35);}
.stButton > button[kind="primary"]:hover {filter: brightness(1.12); box-shadow: 0 10px 30px rgba(79,70,229,.5);}

[data-testid="stFileUploaderDropzone"] {border: 1.5px dashed rgba(96,165,250,.5); background: rgba(59,130,246,.06);
  border-radius: 18px; padding: 28px;}
[data-testid="stChatInput"] {border-radius: 16px;}
[data-testid="stMetric"] {background: var(--fs-panel); border: 1px solid var(--fs-line); border-radius: 16px; padding: 14px 16px;}
[data-testid="stExpander"] details {border-color: var(--fs-line); border-radius: 14px; background: rgba(255,255,255,.02);}
[data-testid="stCaptionContainer"] {color: var(--fs-mute);}

/* hero */
.fs-hero {position: relative; overflow: hidden; border-radius: 26px; padding: 40px 44px; margin-bottom: 20px; color: #fff;
  background: radial-gradient(600px 300px at 85% 10%, rgba(139,92,246,.45), transparent 60%),
              radial-gradient(500px 300px at 10% 110%, rgba(34,211,238,.25), transparent 60%),
              linear-gradient(125deg,#0B1B4D 0%,#1E3A8A 45%,#312E81 100%);
  border: 1px solid rgba(147,197,253,.18); box-shadow: 0 30px 80px rgba(2,6,23,.6), inset 0 1px 0 rgba(255,255,255,.08);}
.fs-hero::before {content: ""; position: absolute; inset: 0; opacity: .25; pointer-events: none;
  background-image: linear-gradient(rgba(255,255,255,.07) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.07) 1px, transparent 1px);
  background-size: 36px 36px; mask-image: linear-gradient(90deg, transparent, #000 60%);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 60%);}
.fs-hero h1 {font-size: 3rem; margin: 0 0 6px 0; font-weight: 900; letter-spacing: -0.03em;
  background: linear-gradient(90deg,#FFFFFF 0%,#BFDBFE 60%,#A5F3FC 100%); -webkit-background-clip: text;
  background-clip: text; color: transparent;}
.fs-hero .sub {font-size: 1.15rem; font-weight: 600; color: #DBEAFE; margin-bottom: 10px;}
.fs-hero p {color: rgba(226,232,240,.82); max-width: 640px; margin: 0; line-height: 1.6;}
.fs-hero .bars {position: absolute; right: 44px; bottom: 0; display: flex; gap: 12px; align-items: flex-end;}
.fs-hero .bars div {width: 30px; border-radius: 9px 9px 0 0;
  background: linear-gradient(180deg,rgba(165,243,252,.95),rgba(59,130,246,.35)); box-shadow: 0 0 24px rgba(34,211,238,.35);}

/* pills */
.fs-pill {display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: .76rem; font-weight: 600;
  background: rgba(59,130,246,.12); color: #93C5FD; border: 1px solid rgba(59,130,246,.32); margin: 2px 6px 2px 0;}
.fs-pill.green {background: rgba(16,185,129,.12); color: #6EE7B7; border-color: rgba(16,185,129,.32);}
.fs-pill.amber {background: rgba(245,158,11,.12); color: #FCD34D; border-color: rgba(245,158,11,.32);}
.fs-pill.red {background: rgba(239,68,68,.12); color: #FCA5A5; border-color: rgba(239,68,68,.32);}

/* cards */
.fs-card {background: linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.02)); border: 1px solid var(--fs-line);
  border-radius: 18px; padding: 16px 18px; box-shadow: 0 10px 30px rgba(2,6,23,.35), inset 0 1px 0 rgba(255,255,255,.05);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;}
.fs-card:hover {transform: translateY(-3px); border-color: rgba(96,165,250,.45);
  box-shadow: 0 16px 40px rgba(2,6,23,.5), 0 0 0 1px rgba(59,130,246,.15), 0 0 30px rgba(59,130,246,.12);}
.fs-company {text-align: center; padding: 20px 10px 16px;}
.fs-company .logo-tile {width: 64px; height: 64px; margin: 0 auto; border-radius: 18px; display: flex; align-items: center;
  justify-content: center; background: radial-gradient(circle at 30% 20%, rgba(255,255,255,.12), rgba(255,255,255,.03));
  border: 1px solid rgba(255,255,255,.08);}
.fs-company .name {font-weight: 700; color: var(--fs-text); margin-top: 10px;}
.fs-company .tick {font-size: .75rem; color: var(--fs-mute); margin-bottom: 10px; letter-spacing: .04em;}
.fs-company .big {font-size: 1.22rem; font-weight: 800; color: #FFFFFF;}
.fs-company .lbl {font-size: .72rem; color: var(--fs-mute); margin-bottom: 6px;}
.fs-kpi .v {font-size: 1.6rem; font-weight: 800; color: #FFFFFF;}
.fs-kpi .l {font-size: .82rem; color: var(--fs-mute);}
.fs-up {color: #34D399; font-weight: 700; font-size: .82rem;}
.fs-down {color: #F87171; font-weight: 700; font-size: .82rem;}
.fs-muted {color: var(--fs-mute); font-size: .86rem;}
.fs-title {color: var(--fs-text);}
.fs-section {font-size: 1.15rem; font-weight: 800; color: var(--fs-text); margin: 22px 0 10px;}
.fs-step {display: flex; gap: 12px; align-items: flex-start; margin-bottom: 10px;}
.fs-step .n {min-width: 28px; height: 28px; border-radius: 9px; background: linear-gradient(135deg,rgba(59,130,246,.3),rgba(139,92,246,.3));
  color: #DBEAFE; font-weight: 800; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(147,197,253,.25);}
.fs-brand {display: flex; align-items: center; gap: 12px;}
.fs-brand .t {font-size: 1.25rem; font-weight: 800; color: var(--fs-text);}
.fs-brand .t span {color: #60A5FA;}
[data-testid="stElementContainer"]:has(.fs-dr-lock) {display: none;}
</style>
"""


DARKREADER_LOCK = """<span class="fs-dr-lock"></span><script>
if (!document.head.querySelector('meta[name="darkreader-lock"]')) {
  const m = document.createElement('meta'); m.name = 'darkreader-lock'; document.head.appendChild(m);
}
</script>"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    # FinSight has its own dark theme. Dark-mode extensions (Dark Reader) repaint it and hide
    # dark logos/text, so ask them to leave the page alone (Dark Reader's official opt-out tag).
    st.html(DARKREADER_LOCK, unsafe_allow_javascript=True)


def page_header(icon_html: str, title: str, subtitle: str) -> None:
    st.markdown(f"<div class='fs-brand' style='margin-bottom:2px'>{icon_html}"
                f"<div><div style='font-size:1.75rem;font-weight:800;color:#EEF2FA'>{title}</div>"
                f"<div class='fs-muted'>{subtitle}</div></div></div>", unsafe_allow_html=True)
    st.write("")


def pill(text: str, tone: str = "") -> str:
    return f"<span class='fs-pill {tone}'>{html.escape(text)}</span>"


def safe_md(text: str) -> str:
    """Streamlit treats text between two $ signs as a LaTeX formula, so escape every $."""
    return (text or "").replace("$", "\\$")


def fmt_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign, v = ("-" if value < 0 else ""), abs(value)
    if v >= 1e9:
        return f"{sign}${v / 1e9:,.2f}B"
    if v >= 1e6:
        return f"{sign}${v / 1e6:,.1f}M"
    return f"{sign}${v:,.0f}"


def delta_html(pct: float | None, suffix: str = "YoY") -> str:
    if pct is None or pd.isna(pct):
        return "<span class='fs-muted'>&nbsp;</span>"
    cls, arrow = ("fs-up", "▲") if pct >= 0 else ("fs-down", "▼")
    return f"<span class='{cls}'>{arrow} {abs(pct):.1f}% {suffix}</span>"


# ---------------- cached API data ----------------
@st.cache_data(ttl=30, show_spinner=False)
def health() -> dict:
    return api_client.health()


@st.cache_data(ttl=300, show_spinner=False)
def companies() -> list[dict]:
    return api_client.companies()


@st.cache_data(ttl=300, show_spinner=False)
def metrics() -> list[dict]:
    return api_client.metrics()


@st.cache_data(ttl=300, show_spinner=False)
def financials(ticker: str) -> dict:
    return api_client.financials(ticker)


def metric_history(fin: dict, metric: str) -> list[dict]:
    for m in fin.get("metrics", []):
        if m["metric"] == metric:
            return m["history"]
    return []


def latest(fin: dict, metric: str) -> dict | None:
    rows = metric_history(fin, metric)
    return rows[-1] if rows else None


# ---------------- sidebar ----------------
def sidebar_status() -> dict | None:
    with st.sidebar:
        try:
            h = health()
        except ApiError as exc:
            st.markdown(pill("● API offline", "red"), unsafe_allow_html=True)
            st.caption(exc.message)
            return None
        tone, label = ("green", "● API online") if h["status"] == "ok" else ("amber", "● Setup incomplete")
        st.markdown(pill(label, tone) + f"<div class='fs-muted' style='margin-top:6px'>{h['sec_chunks']:,} SEC "
                    f"chunks indexed · {h['uploads']} uploads</div>", unsafe_allow_html=True)
        chain = [h["llm_model"], *h["fallback_models"]] + (["Ollama (local)"] if h["ollama_enabled"] else [])
        st.caption("Model chain: " + " → ".join(chain))
        for problem in h.get("problems", []):
            st.caption(f"⚠ {problem}")
        if api_client.PUBLIC_DEMO:
            st.caption("🌐 Public demo · sample files only · shared free AI quota (saved answers are instant)")
        st.caption("FinSight AI v1.0 · research only, not investment advice")
        return h


# ---------------- answers ----------------
ROUTE_LABELS = {"narrative": ("📄 From 10-K text", ""), "numbers": ("🔢 Exact SEC figures", "green"),
                "both": ("🔢 + 📄 Figures and 10-K text", "green"),
                "report": ("📑 Company report · figures + 10-K text", "green")}


def _cell(text) -> str:
    """Safe text for a Markdown table cell."""
    return safe_md(str(text)).replace("|", "\\|").replace("\n", " ")


AGENT_ICONS = {"Spreadsheet Agent": "📗", "Document Agent": "📕"}


def all_calculations(result: dict) -> list[dict]:
    """Level 12: the Spreadsheet Agent may return several results ([T1], [T2]); older answers have one."""
    return result.get("calculations") or ([result["calculation"]] if result.get("calculation") else [])


def render_orchestrator(trace: dict) -> None:
    """Level 12: show who did the work: the Orchestrator's decision and each agent's task."""
    how = "decided by AI (Gemini planner)" if trace["decided_by"] == "ai" else "decided by rules"
    with st.expander(f"🧭 Orchestrator · {len(trace['agents'])} agent(s) · {how}", expanded=False):
        if trace.get("reason"):
            st.caption(safe_md(trace["reason"]))
        for step in trace["agents"]:
            ok = "✅" if step["status"].startswith("done") else "⚠️"   # "done · skipped x.csv" is still done
            st.markdown(f"{ok} {AGENT_ICONS.get(step['agent'], '🤖')} **{step['agent']}** · "
                        f"{_cell(', '.join(step['files']))}  \n<span class='fs-muted'>Task: "
                        f"{html.escape(step['task'])}</span>", unsafe_allow_html=True)
            if step["status"] != "done":
                st.caption(safe_md(step["status"]))


def render_report(rep: dict, key: str) -> None:
    """Level 11: the 10-section Company Report. Sections without data were skipped by the backend."""
    with st.container(border=True):
        st.markdown(f"<div class='fs-brand'>{company_logo_img(rep['ticker'], 40)}<div>"
                    f"<div style='font-size:1.35rem;font-weight:800;color:#EEF2FA'>{html.escape(rep['company'])} · "
                    f"Company Report</div><div class='fs-muted'>Form 10-K FY{rep['fiscal_year']} · period ending "
                    f"{rep['period_end']} · official SEC filings · not investment advice</div></div></div>",
                    unsafe_allow_html=True)
        for s in rep["sections"]:
            st.markdown(f"#### {s['title']}")
            if s.get("note"):
                st.caption(safe_md(s["note"]))
            if s["facts"]:
                lines = ["| Item | Value | Details |", "|---|---|---|"]
                for f in s["facts"]:
                    details = _cell(f.get("note") or "")
                    if f.get("link"):
                        details += f" [open ↗]({f['link']})"
                    lines.append(f"| {_cell(f['label'])} | **{_cell(f['value'])}** | {details} |")
                st.markdown("\n".join(lines))
            if s.get("table"):
                st.dataframe(pd.DataFrame(s["table"]), hide_index=True, width="stretch")
            if s.get("text"):
                st.markdown(safe_md(s["text"]))
        if rep.get("skipped"):
            st.caption("Skipped, because the SEC filings don't contain it: " + ", ".join(rep["skipped"]))
        st.download_button("⬇ Download report", data=rep["markdown"], mime="text/markdown",
                           file_name=f"FinSight_{rep['ticker']}_FY{rep['fiscal_year']}_report.md",
                           key=f"dl_report_{key}")


def render_comparison(comp: dict, chart: bool = False, key: str = "") -> None:
    """One metric across companies (ranked table) or one company across years (trend table)."""
    trend = comp.get("mode") == "trend"
    with st.container(border=True):
        how = "year-over-year change calculated by Python" if trend else "ranked and calculated by Python"
        st.markdown(f"**{comp['label']}** <span class='fs-muted'>· exact values from SEC XBRL data, "
                    f"{how}</span>", unsafe_allow_html=True)
        rows = comp.get("rows") or []
        if not rows:
            st.info("No reported figures for this metric." if trend
                    else "No company in this selection reports this metric.")
        elif trend:   # one company, two years (Level 10)
            table = pd.DataFrame([{
                "Fiscal year": f"FY{r['fiscal_year']}", "Period end": r["period_end"], comp["label"]: r["value_display"],
                "Change": "—" if r.get("yoy_change") is None else
                          ("+" if r["yoy_change"] >= 0 else "-") + fmt_money(abs(r["yoy_change"])),
                "Change %": "—" if r.get("yoy_change_pct") is None else f"{r['yoy_change_pct']:+.2f}%",
                "SEC filing": r["source_url"]} for r in rows])
            st.dataframe(table, hide_index=True, width="stretch", column_config={
                "SEC filing": st.column_config.LinkColumn("SEC filing", display_text="open ↗")})
        else:
            table = pd.DataFrame([{
                "Rank": r.get("rank"), "Company": r["company"], "Fiscal year": f"FY{r['fiscal_year']}",
                "Period end": r["period_end"], comp["label"]: r["value_display"],
                "% of leader": r.get("share_of_leader_pct"), "Derived": "yes" if r.get("derived") else "",
                "SEC filing": r["source_url"]} for r in rows])
            st.dataframe(table, hide_index=True, width="stretch", column_config={
                "SEC filing": st.column_config.LinkColumn("SEC filing", display_text="open ↗"),
                "% of leader": st.column_config.NumberColumn(format="%.2f%%")})
            if chart and len(rows) > 1:
                st.bar_chart(pd.DataFrame({"Company": [f"{r['rank']}. {r['ticker']}" for r in rows],
                                           "USD billions": [round(r["value"] / 1e9, 2) for r in rows]}),
                             x="Company", y="USD billions", color="#3B82F6")
        if comp.get("summary"):
            st.success(safe_md(comp["summary"]))
        for note in comp.get("notes", []):
            st.caption(f"ℹ️ {safe_md(note)}")


def passage_md(text: str) -> str:
    """Show a passage exactly as written (line breaks kept, $ signs safe)."""
    return safe_md(text).replace("\n", "  \n")


@st.cache_data(ttl=600, show_spinner=False)
def section(ticker: str, fiscal_year: int, section_id: str) -> dict:
    return api_client.section(ticker, fiscal_year, section_id)


@st.dialog("📖 Full section from the 10-K", width="large")
def section_dialog(ticker: str, fiscal_year: int, section_id: str) -> None:
    """Level 10: read the whole chapter (e.g. Item 8 with the auditor's report) inside FinSight."""
    try:
        sec = section(ticker, fiscal_year, section_id)
    except ApiError as err:
        st.error(err.message)
        return
    st.markdown(f"**{sec['company']} · Form 10-K FY{sec['fiscal_year']} · {safe_md(sec['section'])}**")
    st.caption(f"Period ending {sec['period_end']} · {sec['char_count']:,} characters · official SEC text")
    find = st.text_input("Find in this section", placeholder="e.g. auditor, opinion, Ernst & Young",
                         key=f"find_{ticker}_{fiscal_year}_{section_id}")
    body = passage_md(sec["text"])
    if find.strip():
        count, body = find_in_section(sec["text"], find)
        st.caption(f"{count} line(s) contain \"{safe_md(find.strip())}\" · shown with the lines around them")
    with st.container(height=480, border=True):
        st.markdown(body)
    st.link_button("Open the original filing on SEC.gov ↗", sec["document_url"])


def find_in_section(text: str, term: str, before: int = 2, after: int = 3) -> tuple[int, str]:
    """Lines containing `term`, each shown WITH the lines around it (the signature line alone says little;
    with its neighbours it shows the date, city and "auditor since"). Returns (matches, markdown)."""
    term, lines = term.strip(), text.split("\n")
    hits = [i for i, line in enumerate(lines) if term and term.lower() in line.lower()]
    blocks, last = [], -1                          # overlapping windows are merged into one block
    for i in hits:
        start, end = max(i - before, last + 1), min(i + after + 1, len(lines))
        if start < end:
            if blocks and start == last + 1:
                blocks[-1] += lines[start:end]
            else:
                blocks.append(lines[start:end])
            last = end - 1
    pattern = re.compile(re.escape(safe_md(term)), re.IGNORECASE)
    shown = [pattern.sub(lambda m: f"**{m.group(0)}**", passage_md("\n".join(b))) for b in blocks]
    return len(hits), "\n\n---\n\n".join(shown) or "No matches."


def render_sources(result: dict, kind: str) -> None:
    """Level 10: each source shows the FULL passage, so the user never has to dig through the website."""
    sources = result.get("sources") or []
    if not sources:
        return
    st.markdown(f"**Sources ({len(sources)})** <span class='fs-muted'>· the exact passages the answer is "
                "based on</span>", unsafe_allow_html=True)
    for i, s in enumerate(sources):
        if kind == "sec":
            label = f"[{s['number']}] {s['company']} · FY{s['fiscal_year']} · {s['section']}"
            with st.expander(label, expanded=(i == 0)):
                st.caption(f"Period ending {s['period_end']} · relevance {s['score']:.2f}")
                with st.container(border=True):
                    st.markdown(passage_md(s.get("text") or s["excerpt"]))
                left, mid, right = st.columns(3)
                with left:
                    if s.get("section_id") and st.button("📖 Read the full section", key=f"sec_{s['number']}_{i}_"
                                                         f"{s['ticker']}_{s['fiscal_year']}_{s['section_id']}",
                                                         width="stretch"):
                        section_dialog(s["ticker"], s["fiscal_year"], s["section_id"])
                with mid:
                    st.link_button("📍 Open at this exact spot ↗", s.get("deep_link") or s["document_url"],
                                   width="stretch",
                                   help="Opens the 10-K on SEC.gov scrolled to this passage, highlighted "
                                        "(Chrome / Edge).")
                with right:
                    st.link_button("Whole filing on SEC.gov ↗", s["document_url"], width="stretch")
        else:
            where = f"page {s['page']}" if s.get("page") else f"sheet {s.get('sheet')}"
            number = f"[{s['number']}] " if s.get("number") else (f"[{s['ref']}] " if s.get("ref") else "")
            with st.expander(f"📎 {number}{s['filename']} · {where}", expanded=(i == 0)):
                if s.get("text") or s.get("excerpt"):
                    with st.container(border=True):
                        st.markdown(passage_md(s.get("text") or s["excerpt"]))
                if s.get("detail"):
                    st.caption(safe_md(s["detail"]))


def render_transparency(result: dict, kind: str) -> None:
    """'How this answer was made' - the pipeline trail, so every answer is auditable."""
    with st.expander("🔍 How this answer was made"):
        unverified = result.get("unverified_numbers") or []
        steps = []
        if kind == "sec":
            route = result.get("route", "narrative")
            steps.append(("Route", ROUTE_LABELS.get(route, (route, ""))[0]))
            steps.append(("Companies", ", ".join(result.get("companies") or []) or "all"))
            if result.get("retrieved_chunks"):
                steps.append(("10-K chunks retrieved", str(result["retrieved_chunks"])))
            if result.get("financials"):
                steps.append(("Exact figures", ", ".join(c["label"] for c in result["financials"])))
        else:
            if result.get("orchestrator"):
                trace = result["orchestrator"]
                steps.append(("Orchestrator", ("Gemini planner" if trace["decided_by"] == "ai" else "rules") + " → "
                              + " + ".join(a["agent"] for a in trace["agents"])))
            steps.append(("Documents", ", ".join(result.get("documents") or [])))
            if all_calculations(result):
                steps.append(("Calculation", "Python (Pandas) - plan below"))
        steps.append(("Model", result.get("model") or "none (no AI call needed)"))
        steps.append(("Cache", "hit - no quota used" if result.get("cached") else "fresh answer"))
        steps.append(("Number guard", "passed - every figure found in the evidence" if not unverified
                      else "flagged: " + ", ".join(unverified)))
        if "guardrails" in result:     # Level 13
            guards = [g for g in result.get("guardrails") or [] if g["action"] != "passed"]
            steps.append(("Guardrails", "all passed (input checks, PII, advice, citations)" if not guards else
                          "; ".join(f"{g['name'].replace('_', ' ')}: {g['action']}"
                                    + (f" ({g['detail']})" if g.get("detail") else "") for g in guards)))
        if result.get("request_id"):
            steps.append(("Request id", f"{result['request_id']} (see the Monitoring page)"))
        for n, (name, value) in enumerate(steps, 1):
            st.markdown(f"<div class='fs-step'><div class='n'>{n}</div><div><b>{name}</b><br>"
                        f"<span class='fs-muted'>{html.escape(str(value))}</span></div></div>",
                        unsafe_allow_html=True)
        for calc in all_calculations(result):
            st.json(calc["plan"])


def render_answer(result: dict, kind: str, key: str) -> None:
    """kind = 'sec' (5 companies) or 'upload' (user files)."""
    st.markdown(safe_md(result["answer"]))
    pills = []
    if kind == "sec" and result.get("route"):
        label, tone = ROUTE_LABELS.get(result["route"], (result["route"], ""))
        pills.append(pill(label, tone))
    if result.get("cached"):
        pills.append(pill("⚡ From cache · no quota used", "amber"))
    if result.get("model"):
        pills.append(pill(f"🤖 {result['model']}"))
    if pills:
        st.markdown(" ".join(pills), unsafe_allow_html=True)

    if result.get("report"):
        render_report(result["report"], key=key)
    for i, comp in enumerate(result.get("financials") or []):
        render_comparison(comp, key=f"{key}_{i}")

    if result.get("orchestrator"):
        render_orchestrator(result["orchestrator"])
    for calc in all_calculations(result):
        with st.container(border=True):
            ref = f"[{calc['ref']}] " if calc.get("ref") else ""
            where = f" · {calc['filename']} / {calc['sheet']}" if calc.get("filename") else ""
            st.markdown(f"**🧮 {ref}Calculation (done by Python, not the AI)**"
                        f"<span class='fs-muted'>{html.escape(where)}</span>", unsafe_allow_html=True)
            st.caption(safe_md(calc["summary"]))
            if calc.get("table"):   # empty cells (e.g. the first year's change) shown as "—", not "None"
                # round floats too: once a column holds "—" it is shown as text, so 46.30000000000001 would leak
                rows = [{k: ("—" if v is None else round(v, 6) if isinstance(v, float) else v)
                         for k, v in r.items()} for r in calc["table"]]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    render_sources(result, kind)
    left, right = st.columns([3, 1])
    with left:
        render_transparency(result, kind)
    with right:
        st.download_button("⬇ Download answer", data=answer_as_text(result), file_name="finsight_answer.md",
                           mime="text/markdown", key=f"dl_{key}", width="stretch")


def answer_as_text(result: dict) -> str:
    lines = ["# FinSight AI answer", "", result["answer"], ""]
    for comp in result.get("financials") or []:
        lines.append(f"## {comp['label']} (exact SEC XBRL figures)")
        lines += [f"- {r['company']}: {r['value_display']} (FY{r['fiscal_year']}, period end {r['period_end']}) "
                  f"{r['source_url']}" for r in comp["rows"]]
        lines += [f"Note: {n}" for n in comp.get("notes", [])]
    for s in result.get("sources") or []:
        if "document_url" in s:
            lines.append(f"- [{s['number']}] {s['company']} FY{s['fiscal_year']} {s['section']}: "
                         f"{s.get('deep_link') or s['document_url']}")
        else:
            lines.append(f"- {s['filename']} " + (f"page {s['page']}" if s.get("page") else f"sheet {s.get('sheet')}"))
        passage = s.get("text") or s.get("excerpt")
        if passage:   # the full passage travels with the answer, so the file is complete on its own
            lines += ["", *[f"  > {line}" for line in passage.splitlines() if line.strip()], ""]
    for calc in all_calculations(result):
        lines += ["", f"Calculation {calc.get('ref', '')} ({calc.get('filename', '')}): {calc['summary']}",
                  "Plan: " + json.dumps(calc["plan"])]
    return "\n".join(lines)


def chat_history(messages: list[dict], kind: str) -> None:
    for i, message in enumerate(messages):
        avatar = "🧑" if message["role"] == "user" else "📊"
        with st.chat_message(message["role"], avatar=avatar):
            if message.get("error"):
                st.error(message["error"])
            elif message.get("result"):
                render_answer(message["result"], kind, key=f"{kind}_{i}")
            else:
                st.markdown(safe_md(message["content"]))


def company_card(ticker: str, name: str, fin: dict | None) -> str:
    rev = latest(fin, "revenue") if fin else None
    ni = latest(fin, "net_income") if fin else None
    fy = f"FY{rev['fiscal_year']}" if rev else ""
    return (f"<div class='fs-card fs-company'><div class='logo-tile'>{company_logo_img(ticker, 36)}</div>"
            f"<div class='name'>{html.escape(name)}</div><div class='tick'>{ticker} · {fy}</div>"
            f"<div class='big'>{fmt_money(rev['value']) if rev else '—'}</div><div class='lbl'>Revenue</div>"
            f"<div class='big' style='font-size:1rem'>{fmt_money(ni['value']) if ni else '—'}</div>"
            f"<div class='lbl'>Net income</div>{delta_html(rev.get('yoy_change_pct') if rev else None)}</div>")


__all__ = ["apply_theme", "page_header", "pill", "safe_md", "fmt_money", "delta_html", "health", "companies",
           "metrics", "financials", "metric_history", "latest", "sidebar_status", "render_comparison",
           "render_answer", "chat_history", "company_card", "TICKERS", "BRAND_COLORS", "company_logo", "company_logo_img",
           "finsight_mark"]
