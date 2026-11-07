"""FinSight AI - Streamlit user interface.

Run from the project root (with the API already running in another terminal):
    streamlit run frontend/app.py

The UI only talks to the FastAPI backend (frontend/api_client.py). All AI and data work happens there.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so "frontend" imports work under streamlit
from frontend import api_client  # noqa: E402
from frontend.api_client import ApiError  # noqa: E402

SEC_MODE, UPLOAD_MODE = "5 public companies (SEC 10-K)", "My uploaded files"
SEC_SUGGESTIONS = [
    "What are NVIDIA's major business risks?",
    "Explain the business segments of Alphabet",
    "Compare the main risks of Apple and Microsoft",
    "Summarize Amazon's annual report",
]
TEXT_SUGGESTIONS = ["Summarize this document", "What was total revenue?", "What are the main risks mentioned?"]
TABLE_SUGGESTIONS = ["What is the net profit margin for each year?", "How did revenue grow year by year?",
                     "What were the biggest expenses?"]

st.set_page_config(page_title="FinSight AI", page_icon="📊", layout="wide")
st.markdown("""<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
.fs-badge {display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.78rem;
           background:rgba(59,130,246,.15); border:1px solid rgba(59,130,246,.4); margin-right:6px;}
</style>""", unsafe_allow_html=True)


# ---------------- state ----------------
def init_state() -> None:
    defaults = {"messages": {SEC_MODE: [], UPLOAD_MODE: []}, "pending": None,
                "uploader_key": 0, "selected_docs": set(), "upload_error": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_data(ttl=30, show_spinner=False)
def cached_health() -> dict:
    return api_client.health()


@st.cache_data(ttl=300, show_spinner=False)
def cached_companies() -> list[dict]:
    return api_client.companies()


# ---------------- rendering ----------------
def render_answer(result: dict, mode: str) -> None:
    st.markdown(result["answer"])

    badges = []
    if result.get("cached"):
        badges.append("⚡ from cache (no quota used)")
    if result.get("model"):
        badges.append(f"🤖 {result['model']}")
    if mode == SEC_MODE and result.get("retrieved_chunks"):
        badges.append(f"📄 {result['retrieved_chunks']} chunks retrieved")
    if badges:
        st.markdown(" ".join(f"<span class='fs-badge'>{b}</span>" for b in badges), unsafe_allow_html=True)

    if result.get("unverified_numbers"):
        st.warning("These figures were not found in the sources: "
                   + ", ".join(result["unverified_numbers"]) + ". Verify them before relying on them.")

    calc = result.get("calculation")
    if calc:
        st.markdown("**Calculation (done by Python, not the AI)**")
        st.caption(calc["summary"])
        if calc.get("table"):
            st.dataframe(pd.DataFrame(calc["table"]), hide_index=True, width="stretch")
        with st.expander("Calculation plan (JSON chosen by the AI, checked by Python)"):
            st.json(calc["plan"])

    sources = result.get("sources") or []
    if sources:
        st.markdown(f"**Sources ({len(sources)})**")
        for s in sources:
            if mode == SEC_MODE:
                label = f"[{s['number']}] {s['company']} · FY{s['fiscal_year']} · {s['section']}"
                with st.expander(label):
                    st.caption(f"Period ending {s['period_end']} · relevance {s['score']:.2f}")
                    st.markdown(f"> {s['excerpt']}…")
                    st.link_button("Open original SEC filing ↗", s["document_url"])
            else:
                where = f"page {s['page']}" if s.get("page") else f"sheet {s.get('sheet')}"
                number = f"[{s['number']}] " if s.get("number") else ""
                with st.expander(f"{number}{s['filename']} · {where}"):
                    if s.get("excerpt"):
                        st.markdown(f"> {s['excerpt']}…")
                    if s.get("detail"):
                        st.caption(s["detail"])


def render_history(mode: str) -> None:
    for message in st.session_state.messages[mode]:
        with st.chat_message(message["role"], avatar="🧑" if message["role"] == "user" else "📊"):
            if message.get("error"):
                st.error(message["error"])
            elif message.get("result"):
                render_answer(message["result"], mode)
            else:
                st.markdown(message["content"])


# ---------------- sidebar ----------------
def sidebar_status() -> dict | None:
    try:
        health = cached_health()
    except ApiError as exc:
        st.sidebar.error(exc.message)
        return None
    if health["status"] == "ok":
        st.sidebar.success(f"API online · {health['sec_chunks']:,} SEC chunks indexed")
    else:
        st.sidebar.warning("API online, but setup is incomplete:\n\n- " + "\n- ".join(health["problems"]))
    chain = " → ".join([health["llm_model"], *health["fallback_models"]]
                       + (["Ollama (local)"] if health["ollama_enabled"] else []))
    st.sidebar.caption(f"Model chain: {chain}")
    return health


def sidebar_sec() -> str | None:
    try:
        companies = cached_companies()
    except ApiError as exc:
        st.sidebar.error(exc.message)
        return None
    options = {"All companies (detect from question)": None}
    for c in companies:
        years = ", ".join(f"FY{y}" for y in c["fiscal_years"]) or "no reports yet"
        options[f"{c['name']} ({c['ticker']}) · {years}"] = c["ticker"]
    choice = st.sidebar.selectbox("Company", list(options))
    st.sidebar.caption("Fiscal years end on different dates (e.g. Apple: September, Microsoft: June), "
                       "so answers always state the period.")
    return options[choice]


def sidebar_uploads() -> tuple[list[str], str | None, list[dict]]:
    uploaded = st.sidebar.file_uploader(
        "Upload a financial document", type=["pdf", "txt", "docx", "csv", "xlsx"],
        key=f"uploader_{st.session_state.uploader_key}",
        help="Max 10 MB. Scanned PDFs can't be read. Use public or sample data only.")
    if uploaded is not None:
        with st.sidebar.status(f"Processing {uploaded.name}…") as box:
            try:
                meta = api_client.upload(uploaded.name, uploaded.getvalue())
                st.session_state.selected_docs = {meta["doc_id"]}
                box.update(label=f"Uploaded {uploaded.name}", state="complete")
                st.toast(f"✅ {uploaded.name} is ready", icon="📄")
            except ApiError as exc:
                box.update(label="Upload failed", state="error")
                # kept in session_state: anything drawn now is wiped by the st.rerun() below
                st.session_state.upload_error = f"{uploaded.name}: {exc.message}"
        st.session_state.uploader_key += 1      # reset the widget so the file isn't uploaded twice
        st.rerun()
    if st.session_state.upload_error:          # show an upload/delete error once, after the rerun
        st.sidebar.error(st.session_state.upload_error)
        st.session_state.upload_error = None

    try:
        uploads = api_client.list_uploads()
    except ApiError as exc:
        st.sidebar.error(exc.message)
        return [], None, []
    if not uploads:
        st.sidebar.info("No files yet. Upload one above, or try the files in the samples/ folder.")
        return [], None, []

    st.sidebar.markdown("**Ask about:**")
    selected = []
    for u in uploads:
        icon = "📊" if u["kind"] == "table" else "📄"
        size = (f"{u['tables'][0]['rows']} rows" if u["kind"] == "table" else f"{u['pages']} page(s)")
        cols = st.sidebar.columns([5, 1])
        checked = cols[0].checkbox(f"{icon} {u['filename']} · {size}", key=f"pick_{u['doc_id']}",
                                   value=u["doc_id"] in st.session_state.selected_docs)
        if cols[1].button("✕", key=f"del_{u['doc_id']}", help="Delete this upload"):
            try:
                api_client.delete_upload(u["doc_id"])
                st.session_state.selected_docs.discard(u["doc_id"])
            except ApiError as exc:
                st.session_state.upload_error = exc.message
            st.rerun()
        if checked:
            selected.append(u["doc_id"])
    st.session_state.selected_docs = set(selected)

    sheet = None
    chosen = [u for u in uploads if u["doc_id"] in selected]
    if len(chosen) == 1 and chosen[0]["kind"] == "table" and len(chosen[0]["tables"]) > 1:
        sheet = st.sidebar.selectbox("Sheet", [t["sheet"] for t in chosen[0]["tables"]])
    return selected, sheet, chosen


# ---------------- main ----------------
def ask(mode: str, question: str, ticker: str | None, doc_ids: list[str], sheet: str | None,
        use_cache: bool) -> None:
    history = st.session_state.messages[mode]
    history.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="📊"):
        try:
            with st.spinner("Searching the documents and writing a grounded answer…"):
                if mode == SEC_MODE:
                    result = api_client.chat(question, ticker, use_cache)
                else:
                    result = api_client.ask_uploads(question, doc_ids, sheet, use_cache)
            render_answer(result, mode)
            history.append({"role": "assistant", "content": result["answer"], "result": result})
        except ApiError as exc:
            st.error(exc.message)
            history.append({"role": "assistant", "content": "", "error": exc.message})


def suggestions(mode: str, chosen: list[dict]) -> None:
    if mode == SEC_MODE:
        items = SEC_SUGGESTIONS
    elif chosen and all(c["kind"] == "table" for c in chosen):
        items = TABLE_SUGGESTIONS
    elif chosen:
        items = TEXT_SUGGESTIONS
    else:
        return
    st.markdown("**Try a question:**")
    cols = st.columns(len(items))
    for col, text in zip(cols, items):
        if col.button(text, width="stretch"):
            st.session_state.pending = text
            st.rerun()


def main() -> None:
    init_state()
    st.sidebar.title("📊 FinSight AI")
    health = sidebar_status()
    mode = st.sidebar.radio("Ask about", [SEC_MODE, UPLOAD_MODE])
    st.sidebar.divider()

    ticker, doc_ids, sheet, chosen = None, [], None, []
    if health is not None:
        if mode == SEC_MODE:
            ticker = sidebar_sec()
        else:
            doc_ids, sheet, chosen = sidebar_uploads()
    st.sidebar.divider()
    use_cache = st.sidebar.toggle("Use saved answers (saves quota)", value=True)
    if st.sidebar.button("🧹 Clear conversation", width="stretch"):
        st.session_state.messages[mode] = []
        st.rerun()

    st.title("FinSight AI")
    if mode == SEC_MODE:
        st.caption("Evidence-backed answers from official SEC 10-K filings of Apple, Microsoft, Amazon, "
                   "Alphabet and NVIDIA. Research only, not investment advice.")
    else:
        st.caption("Answers come only from the files you select. Tables are calculated exactly by Python. "
                   "Use public or sample data only.")

    if health is None:
        st.error("The FinSight API is not running. In another terminal, run:  "
                 "`uvicorn backend.main:app --port 8000`  and then refresh this page.")
        return

    placeholder = "Ask about the companies' annual reports…" if mode == SEC_MODE else "Ask about your files…"
    question = st.chat_input(placeholder) or st.session_state.pending
    st.session_state.pending = None

    render_history(mode)
    if not st.session_state.messages[mode] and not question:
        suggestions(mode, chosen)
    if question:
        if mode == UPLOAD_MODE and not doc_ids:
            st.warning("Select at least one uploaded file in the sidebar first.")
            return
        ask(mode, question, ticker, doc_ids, sheet, use_cache)

main()
