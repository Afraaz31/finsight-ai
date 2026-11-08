"""Upload & Analyze: add your own financial files and ask questions about them.

Level 12: one chat for all files. The Orchestrator sends Excel/CSV questions to the Spreadsheet Agent and
PDF/Word/TXT questions to the Document Agent, or to both. Ticking files is optional (nothing ticked = all).
"""
from pathlib import Path

import streamlit as st

from frontend import api_client, ui
from frontend.api_client import ApiError

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
SAMPLES = [("📄 Annual report (PDF)", "kestrel_annual_report.pdf"),
           ("📝 Board memo (TXT)", "kestrel_board_memo.txt"),
           ("📊 Financials (CSV)", "kestrel_financials.csv"),
           ("📗 Statements (XLSX)", "kestrel_statements.xlsx")]
ICONS = {".pdf": "📕", ".txt": "📝", ".docx": "📘", ".csv": "📊", ".xlsx": "📗"}
TEXT_SUGGESTIONS = ["Summarize this document", "What was revenue and how much did it grow?",
                    "What are the main risks mentioned?"]
TABLE_SUGGESTIONS = ["What is the net profit margin for each year?", "How did revenue grow year by year?",
                     "What were the biggest expenses?"]
MIXED_SUGGESTIONS = ["Does the revenue in the spreadsheet match the annual report?",
                     "Calculate revenue growth and explain what the report says caused it",
                     "What are the main risks mentioned?"]
AUTO_SHEET = "Auto (the Spreadsheet Agent picks the sheet)"


def do_upload(name: str, data: bytes) -> None:
    try:
        api_client.upload(name, data)      # not auto-ticked: nothing ticked = the Orchestrator uses every file
        st.toast(f"✅ {name} is ready", icon="📄")
        ui.health.clear()
    except ApiError as exc:
        st.session_state.upload_error = f"{name}: {exc.message}"   # shown after the rerun


ui.page_header(ui.finsight_mark(44), "Upload & Analyze",
               "Ask about your own files in plain English. The Orchestrator sends Excel/CSV questions to the "
               "Spreadsheet Agent and PDF/Word/TXT questions to the Document Agent, or to both.")

left, right = st.columns([3, 2], gap="large")
with left:
    uploaded = st.file_uploader("Drag & drop a file here, or click to browse",
                                type=["pdf", "txt", "docx", "csv", "xlsx"],
                                key=f"uploader_{st.session_state.uploader_key}",
                                help="Max 10 MB. Scanned PDFs can't be read. Use public or sample data only.")
    if uploaded is not None:
        with st.spinner(f"Reading {uploaded.name}…"):
            do_upload(uploaded.name, uploaded.getvalue())
        st.session_state.uploader_key += 1          # reset the widget so the file isn't sent twice
        st.rerun()
    if st.session_state.upload_error:
        st.error(st.session_state.upload_error)
        st.session_state.upload_error = None

    st.markdown("<span class='fs-muted'>No file at hand? Try a fictional sample:</span>", unsafe_allow_html=True)
    sample_cols = st.columns(2) + st.columns(2)          # 2 x 2 grid, so the labels fit
    for col, (label, filename) in zip(sample_cols, SAMPLES):
        path = SAMPLES_DIR / filename
        if col.button(label, key=f"sample_{filename}", width="stretch", disabled=not path.exists()):
            with st.spinner(f"Uploading {filename}…"):
                do_upload(filename, path.read_bytes())
            st.rerun()

with right:
    try:
        uploads = api_client.list_uploads()
    except ApiError as exc:
        st.error(exc.message)
        uploads = []
    with st.container(border=True):
        st.markdown(f"**Your files ({len(uploads)})** <span class='fs-muted'>· tick files to focus on, or none "
                    "to let the Orchestrator use all of them</span>", unsafe_allow_html=True)
        if not uploads:
            st.caption("No files yet. Upload one, or try a sample.")
        selected = []
        for u in uploads:
            if u["kind"] == "table":
                detail = f"{sum(t['rows'] for t in u['tables'])} rows · {len(u['tables'])} sheet(s)"
            else:
                detail = f"{u['pages']} page(s) · {u['chunks']} chunks"
            row = st.columns([6, 1])
            checked = row[0].checkbox(f"{ICONS.get(u['extension'], '📄')} **{u['filename']}**  \n{detail} · "
                                      f"{max(u['size_bytes'] / 1024, 0.1):,.1f} KB", key=f"pick_{u['doc_id']}",
                                      value=u["doc_id"] in st.session_state.selected_docs)
            if row[1].button("✕", key=f"del_{u['doc_id']}", help="Delete this file"):
                try:
                    api_client.delete_upload(u["doc_id"])
                    st.session_state.selected_docs.discard(u["doc_id"])
                    ui.health.clear()
                except ApiError as exc:
                    st.session_state.upload_error = exc.message
                st.rerun()
            if checked:
                selected.append(u["doc_id"])
        st.session_state.selected_docs = set(selected)

chosen = [u for u in uploads if u["doc_id"] in selected]
scope = chosen or uploads                  # nothing ticked -> the Orchestrator considers every file
sheet = None
if len(chosen) == 1 and chosen[0]["kind"] == "table" and len(chosen[0]["tables"]) > 1:
    pick = st.selectbox("Sheet", [AUTO_SHEET] + [t["sheet"] for t in chosen[0]["tables"]])
    sheet = None if pick == AUTO_SHEET else pick

st.markdown("<div class='fs-section'>Ask your documents</div>", unsafe_allow_html=True)
history = st.session_state.messages["upload"]
question = st.chat_input("Ask about your files in plain English…") or st.session_state.upload_pending
st.session_state.upload_pending = None

if scope and not history and not question:
    kinds = {u["kind"] for u in scope}
    items = MIXED_SUGGESTIONS if len(kinds) > 1 else TABLE_SUGGESTIONS if kinds == {"table"} else TEXT_SUGGESTIONS
    cols = st.columns(len(items))
    for col, q in zip(cols, items):
        if col.button(q, key=f"up_sugg_{q}", width="stretch"):
            st.session_state.upload_pending = q
            st.rerun()
elif not scope:
    st.info("Upload a file (or try a sample) to start asking.")

ui.chat_history(history, "upload")
if question:
    if not uploads:
        st.warning("Upload a file first.")
    else:
        history.append({"role": "user", "content": question})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(ui.safe_md(question))
        with st.chat_message("assistant", avatar="📊"):
            try:
                with st.spinner("🧭 Orchestrator is asking the agents…"):
                    result = api_client.ask_assistant(question, selected, sheet, True)
                ui.render_answer(result, "upload", key=f"upload_{len(history)}")
                history.append({"role": "assistant", "content": result["answer"], "result": result})
            except ApiError as exc:
                st.error(exc.message)
                history.append({"role": "assistant", "content": "", "error": exc.message})
