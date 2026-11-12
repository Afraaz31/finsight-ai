"""How it works: the architecture and safeguards, explained on one page (great for the interview)."""
import pandas as pd
import streamlit as st

from frontend import api_client, ui

ui.page_header(ui.finsight_mark(44), "How FinSight works",
               "Two data pipelines, a question router, and guards that keep every answer verifiable")


def card(col, icon: str, title: str, lines: list[str]) -> None:
    body = "".join(f"<div class='fs-muted' style='margin:3px 0'>• {line}</div>" for line in lines)
    col.markdown(f"<div class='fs-card' style='height:100%'><div style='font-size:1.4rem'>{icon}</div>"
                 f"<div style='font-weight:800;color:#EEF2FA;margin:4px 0 6px'>{title}</div>{body}</div>",
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

st.markdown("<div class='fs-section'>4 · Orchestrator + 2 agents</div>", unsafe_allow_html=True)
st.code("""             user question (plain English)
                          │
                          ▼
         ┌──────────────────────────────────┐
         │           ORCHESTRATOR           │
         │ 1. reads the question + files    │
         │ 2. decides: which agent(s),      │
         │    which files, what task        │
         └───────┬──────────────────┬───────┘
                 ▼                  ▼
  ┌──────────────────────┐  ┌──────────────────────┐
  │  SPREADSHEET AGENT   │  │    DOCUMENT AGENT    │
  │ Excel / CSV          │  │ PDF / Word / TXT     │
  │ Gemini → JSON plan   │  │ search the passages  │
  │ Pandas → exact maths │  │ (RAG, ChromaDB)      │
  │ results [T1], [T2]   │  │ passages [1], [2]    │
  └──────────┬───────────┘  └───────────┬──────────┘
             └────────────┬─────────────┘
                          ▼
         ┌──────────────────────────────────┐
         │ ORCHESTRATOR: combine + check    │
         │ one answer with [T1] and [1]     │
         │ number guard on every figure     │
         └──────────────────────────────────┘""", language=None)
c = st.columns(3)
card(c[0], "🧭", "Orchestrator", ["The only part that talks to you", "One small Gemini call returns a JSON plan: "
                                 "which agent, which files, what task", "Python validates the plan; if the AI is "
                                 "down, rules decide (spreadsheets → Spreadsheet Agent, documents → Document Agent)"])
card(c[1], "📗", "Spreadsheet Agent", ["Several spreadsheets at once, results [T1], [T2]",
                                      "Picks the right sheet in a multi-sheet Excel file",
                                      "Gemini plans, Pandas calculates"])
card(c[2], "📕", "Document Agent", ["Finds the passages in PDF / Word / TXT", "Cites file and page [1], [2]",
                                   "Both agents needed → the Orchestrator merges one cited answer"])

st.markdown("<div class='fs-section'>5 · Observability and guardrails</div>", unsafe_allow_html=True)
st.markdown("<div class='fs-muted'><b>Observability</b> = seeing what the system did, and why, for every request: "
            "route, timed steps, which AI model answered, tokens, cache hits, failures and fallbacks. "
            "<b>Guardrails</b> = checks around the AI that stop bad things going in or coming out.</div>",
            unsafe_allow_html=True)
st.code("""question
   │
   ▼
[rate limit]  (too many per minute → 429)
   │
   ▼
[INPUT guardrails]  injection / advice / off-topic → 400, no AI call
   │
   ▼
service (chat / report / orchestrator)
   │
   ▼
llm_service: [PII redaction] + [daily budget] ──► Gemini (fallback chain)
   │
   ▼
number guard + [OUTPUT guardrails]  advice → disclaimer, leak → replaced,
   │                                PII → redacted, no citations → flagged
   ▼
answer + guardrails + request_id

Every step above is recorded in ONE TRACE per request
  → data/observability/traces.jsonl → Monitoring page""", language=None)
GUARDRAILS = [
    ("1", "Prompt injection (“ignore previous instructions”, “reveal your prompt”, “you are now…”)", "input",
     "blocked → HTTP 400"),
    ("2", "Investment advice (“should I buy…”, “price target”, “will the stock go up”)", "input",
     "blocked, with a helpful alternative"),
    ("3", "Clearly off-topic (“write me a poem”, recipes, hacking)", "input", "blocked"),
    ("4", "PII: emails, Indian/US phones, card numbers (Luhn-checked), Aadhaar, PAN, SSN", "every AI call",
     "redacted before it leaves the laptop; financial figures untouched"),
    ("5", "Daily AI budget (400 calls, under the 500/day free quota)", "every AI call",
     "Gemini skipped → Ollama / Python-only answers still work"),
    ("6", "Rate limit (20 questions per minute per client)", "API, AI endpoints", "HTTP 429 with Retry-After"),
    ("7", "Advice language in the answer (“you should buy…”)", "output", "disclaimer added"),
    ("8", "System-prompt leak (the answer repeats hidden rules)", "output", "answer replaced"),
    ("9", "PII in the answer", "output", "redacted"),
    ("10", "An answer that has sources but cites none", "output", "flagged"),
    (r"\+", "Number guard (every figure checked), plan validation (Orchestrator)", "output",
     "already existed; now visible in every trace"),
]
st.table(pd.DataFrame([{"#": n, "Guardrail": g, "Where": w, "Action": a}
                       for n, g, w, a in GUARDRAILS]).set_index("#"))      # static: every row, wrapped text
st.caption("Plain Python rules: instant, free, deterministic and tested. Every request's trace (and every guardrail "
           "action) is on the Monitoring page; GET /observability/summary and /observability/traces serve the same data.")

st.markdown("<div class='fs-section'>6 · Safeguards</div>", unsafe_allow_html=True)
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
st.caption("API documentation: http://127.0.0.1:8000/docs" + (" (when you run FinSight locally)"
                                                                if api_client.PUBLIC_DEMO else ""))
