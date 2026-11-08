"""Ask AI: chat about the 5 companies (10-K text, exact SEC figures, or both)."""
import streamlit as st

from frontend import api_client, ui
from frontend.api_client import ApiError

SUGGESTIONS = {
    ("📄 From 10-K text", ""): ["What are NVIDIA's major business risks?",
                               "Explain the business segments of Alphabet",
                               "Summarize the management discussion in Apple's annual report"],
    ("🔢 Exact SEC figures", "green"): ["Compare Apple's revenue with Microsoft's",
                                       "Which company reported the highest net income?",
                                       "Compare the financial performance of all five companies"],
    ("🔢 + 📄 Both", "green"): ["Explain Amazon's operating income",
                               "Audit report of Apple",
                               "Explain NVIDIA's revenue growth"],
}

ui.page_header(ui.finsight_mark(44), "Ask FinSight AI",
               "Questions about Apple, Microsoft, Amazon, Alphabet and NVIDIA, answered from their SEC 10-K filings")

companies = ui.companies()
options = {"All companies (detect from the question)": None}
options.update({f"{c['name']} ({c['ticker']})": c["ticker"] for c in companies})
c1, c2, c3 = st.columns([3, 2, 1])
choice = c1.selectbox("Company", list(options), label_visibility="collapsed")
use_cache = c2.toggle("Use saved answers (saves quota)", value=True)
if c3.button("🧹 Clear chat", width="stretch"):
    st.session_state.messages["sec"] = []
    st.rerun()
ticker = options[choice]

history = st.session_state.messages["sec"]
question = st.chat_input("Ask about revenue, risks, segments, comparisons…") or st.session_state.ask_pending
st.session_state.ask_pending = None

if not history and not question:
    st.markdown("<div class='fs-section'>Try a question</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for col, ((label, tone), items) in zip(cols, SUGGESTIONS.items()):
        with col:
            with st.container(border=True):
                st.markdown(ui.pill(label, tone), unsafe_allow_html=True)
                for q in items:
                    if st.button(q, key=f"sugg_{q}", width="stretch"):
                        st.session_state.ask_pending = q
                        st.rerun()

ui.chat_history(history, "sec")

if question:
    history.append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(ui.safe_md(question))
    with st.chat_message("assistant", avatar="📊"):
        try:
            with st.spinner("Routing your question, retrieving evidence and writing a grounded answer…"):
                result = api_client.chat(question, ticker, use_cache)
            ui.render_answer(result, "sec", key=f"sec_{len(history)}")
            history.append({"role": "assistant", "content": result["answer"], "result": result})
        except ApiError as exc:
            st.error(exc.message)
            history.append({"role": "assistant", "content": "", "error": exc.message})
