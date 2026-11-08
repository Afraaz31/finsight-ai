"""Home: what FinSight is, the 5 companies at a glance, and quick ways in."""
import streamlit as st

from frontend import ui
from frontend.api_client import ApiError

HOME_QUESTIONS = [
    "What are NVIDIA's major business risks?",
    "Compare Apple's revenue with Microsoft's",
    "Which company reported the highest net income?",
    "Explain Amazon's operating income",
]

st.markdown(f"""
<div class="fs-hero">
  <div class="fs-brand" style="margin-bottom:10px">{ui.finsight_mark(54)}</div>
  <h1>FinSight AI</h1>
  <div class="sub">Your evidence-backed financial research assistant</div>
  <p>Ask questions about the official SEC 10-K reports of five of the world's largest companies, compare their
  exact reported figures, or upload your own financial documents. Every answer shows its sources, and every
  number comes from the filings or an exact Python calculation, never from the AI's imagination.</p>
  <div class="bars"><div style="height:50px"></div><div style="height:78px"></div><div style="height:104px"></div>
  <div style="height:136px"></div><div style="height:170px"></div></div>
</div>""", unsafe_allow_html=True)

c1, c2, c3, _ = st.columns([1, 1, 1, 2])
if c1.button("💬  Ask a question", type="primary", width="stretch"):
    st.switch_page("views/ask.py")
if c2.button("📂  Upload files", width="stretch"):
    st.switch_page("views/upload.py")
if c3.button("📊  Compare companies", width="stretch"):
    st.switch_page("views/compare.py")

st.markdown("<div class='fs-section'>Companies covered · latest reported fiscal year</div>", unsafe_allow_html=True)
try:
    names = {c["ticker"]: c["name"] for c in ui.companies()}
except ApiError as exc:
    st.error(exc.message)
    st.stop()
cols = st.columns(5)
for col, ticker in zip(cols, ui.TICKERS):
    with col:
        try:
            fin = ui.financials(ticker)
        except ApiError:
            fin = None
        st.markdown(ui.company_card(ticker, names.get(ticker, ticker), fin), unsafe_allow_html=True)
        if st.button("Dashboard →", key=f"dash_{ticker}", width="stretch"):
            st.session_state.dash_ticker = ticker
            st.switch_page("views/dashboard.py")
st.caption("Figures: SEC XBRL Company Facts, original 10-K values. Fiscal years end on different dates "
           "(Apple: September · Microsoft: June · NVIDIA: January · Amazon & Alphabet: December).")

left, right = st.columns([3, 2], gap="large")
with left:
    with st.container(border=True):
        st.markdown("<div style='text-align:center;padding:8px 0'>"
                    "<div style='font-size:2.2rem'>☁️</div>"
                    "<div style='font-weight:800;font-size:1.1rem;color:#EEF2FA'>Analyse your own financial documents</div>"
                    "<div class='fs-muted'>PDF · TXT · DOCX · CSV · XLSX · up to 10 MB. Text files are answered with "
                    "citations; spreadsheets are calculated exactly with Python.</div></div>", unsafe_allow_html=True)
        if st.button("Upload or try a sample file", type="primary", width="stretch"):
            st.switch_page("views/upload.py")
with right:
    with st.container(border=True):
        st.markdown("**Try asking**")
        for q in HOME_QUESTIONS:
            if st.button(q, key=f"home_q_{q}", width="stretch"):
                st.session_state.ask_pending = q
                st.switch_page("views/ask.py")

f1, f2, f3 = st.columns(3)
for col, (icon, title, text) in zip((f1, f2, f3), [
        ("📑", "Evidence-backed answers", "Every claim cites the 10-K section or your file and page, with a link to "
                                          "the original SEC filing."),
        ("🔢", "Exact numbers only", "Figures come from SEC XBRL data or Pandas calculations. A number guard flags "
                                    "anything the AI can't back up."),
        ("🛡️", "Honest by design", "Unsupported companies, unreported metrics and scanned PDFs are stated clearly, "
                                  "never guessed.")]):
    col.markdown(f"<div class='fs-card' style='height:100%'><div style='font-size:1.5rem'>{icon}</div>"
                 f"<div style='font-weight:700;color:#EEF2FA;margin:4px 0'>{title}</div>"
                 f"<div class='fs-muted'>{text}</div></div>", unsafe_allow_html=True)
