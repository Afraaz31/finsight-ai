"""How it works: the architecture and safeguards, explained on one page (great for the interview)."""
import streamlit as st

from frontend import ui

ui.page_header(ui.finsight_mark(44), "How FinSight works",
               "Two data pipelines, a question router, and guards that keep every answer verifiable")


def card(col, icon: str, title: str, lines: list[str]) -> None:
    body = "".join(f"<div class='fs-muted' style='margin:3px 0'>• {line}</div>" for line in lines)
    col.markdown(f"<div class='fs-card' style='height:100%'><div style='font-size:1.4rem'>{icon}</div>"
                 f"<div style='font-weight:800;color:#0F172A;margin:4px 0 6px'>{title}</div>{body}</div>",
                 unsafe_allow_html=True)


st.markdown("<div class='fs-section'>1 · Your question is routed</div>", unsafe_allow_html=True)
c = st.columns(3)
card(c[0], "📄", "Narrative → RAG", ["“What are NVIDIA's risks?”", "Searches 10-K text by meaning",
                                     "Answer cites [n] sections + SEC links"])
card(c[1], "🔢", "Numbers → exact figures", ["“Compare Apple's revenue with Microsoft's”", "SEC XBRL Company Facts",
                                             "Python ranks and calculates"])
card(c[2], "🔢+📄", "Both", ["“Explain Amazon's operating income”", "Exact figure [F] + 10-K explanation [n]",
                            "One grounded answer"])

st.markdown("<div class='fs-section'>2 · The two pipelines</div>", unsafe_allow_html=True)
c = st.columns(2)
card(c[0], "🔎", "Pipeline A · RAG over 10-K text",
     ["Latest 2 annual reports per company from SEC EDGAR", "HTML cleaned and split into 10-K sections",
      "800-character chunks with overlap", "Local embeddings (all-MiniLM-L6-v2, 384 numbers)",
      "ChromaDB cosine search, filtered per company and section", "Gemini answers only from the retrieved sources"])
card(c[1], "📐", "Pipeline B · Structured SEC figures",
     ["SEC XBRL Company Facts (official tagged values)", "Each 10-K's own fiscal year only: no repeats, quarters "
      "or amendments", "Best tag per year; missing values are never filled", "Pandas ranks, compares and "
      "calculates % differences", "Fiscal-year differences are always flagged"])

st.markdown("<div class='fs-section'>3 · Your own files</div>", unsafe_allow_html=True)
c = st.columns(2)
card(c[0], "📕", "PDF · TXT · DOCX", ["Checked: type, size, real file signature, no macros",
                                    "Text extracted page by page (scanned PDFs refused)",
                                    "Separate collection: never mixed with SEC data", "Answers cite file + page"])
card(c[1], "📗", "CSV · XLSX", ["Real header found, $1,234 and (500) cleaned", "Wide year columns reshaped to long",
                              "The AI only picks an operation from a whitelist (JSON)",
                              "Python validates and calculates: no AI code is ever run"])

st.markdown("<div class='fs-section'>4 · Safeguards</div>", unsafe_allow_html=True)
c = st.columns(4)
card(c[0], "🧾", "Citations", ["Every claim tagged [n]", "Code checks that each cited source exists"])
card(c[1], "🛡️", "Number guard", ["Every figure in an answer is checked against the evidence",
                                 "Unverified numbers get a warning"])
card(c[2], "🔁", "Quota Shield", ["3 free Gemini models with separate quotas", "Answer cache + local Ollama backup"])
card(c[3], "🙅", "Honest refusals", ["Unsupported companies, unreported metrics", "No investment advice"])

st.markdown("<div class='fs-section'>Tech stack</div>", unsafe_allow_html=True)
st.markdown(" ".join(ui.pill(t) for t in ["Python 3.11", "FastAPI", "Pydantic", "Streamlit", "Gemini (free tier)",
                                          "Ollama", "Sentence Transformers", "ChromaDB", "Pandas", "BeautifulSoup",
                                          "pypdf", "SEC EDGAR", "SEC XBRL", "pytest"]), unsafe_allow_html=True)
st.caption("API documentation: http://127.0.0.1:8000/docs")
