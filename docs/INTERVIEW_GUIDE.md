# FinSight AI — Interview Guide

How to present, demo and defend the project. Read it twice, then practise the demo out loud once.

---

## 1. The pitch

### 30 seconds

> "FinSight AI is a financial research assistant. It reads the official SEC annual reports of Apple, Microsoft, Amazon, Alphabet and NVIDIA, plus any financial file you upload, and answers questions in plain English **with citations**. The key design rule is that **numbers never come from the AI**. Narrative questions use RAG over the 10-K text, numeric questions use SEC's structured XBRL data and Pandas, and the LLM only explains the results. It runs entirely on free tools: a FastAPI backend, a Streamlit UI, ChromaDB, local embeddings and Gemini's free tier, with a fallback chain and a local Ollama model as backup."

### 2 minutes (what, why, how, proof)

1. **Problem:** annual reports are hundreds of pages long, and general chatbots hallucinate figures with no sources. That isn't acceptable in finance.
2. **Two pipelines:**
   - **RAG** for text: chunk the 10-Ks, embed them locally, store them in ChromaDB, retrieve per company, and let Gemini answer only from the sources, with `[n]` citations and SEC links.
   - **Structured data** for numbers: SEC XBRL Company Facts, deduplicated to each filing's own fiscal year, compared with Pandas.
3. **Router:** a keyword router sends each question to narrative, numbers or both.
4. **Uploads:**
   - PDF, TXT and DOCX files go through the same RAG engine in a separate collection.
   - For CSV and Excel files, the LLM picks an operation as a whitelisted JSON plan and Python calculates. AI-generated code is never executed.
5. **Reliability:**
   - a number guard checks every figure against the evidence
   - a Quota Shield (model fallback chain, answer cache, local Ollama)
   - honest refusals: scanned PDFs, unsupported companies, unreported metrics
6. **Proof:**
   - **187 automated tests**, using no API quota.
   - Apple's FY2026 revenue (**$478.83B**) matches the 10-K exactly in both pipelines.

---

## 2. Demo script (8–10 minutes)

**Before the interview:**
- Run `python -m scripts.preflight` (it should say READY), then `python -m scripts.prewarm`.
- Start everything with `run_demo.ps1`.
- Close extra Chrome tabs.

| # | Do | Say |
|---|---|---|
| 1 | **Home**: point at the 5 company cards | "FinSight covers Apple, Microsoft, Amazon, Alphabet and NVIDIA. These figures come straight from SEC XBRL data: Apple's latest revenue is $478.83B. The left navigation shows the six areas of the app." |
| 2 | Click **"What are NVIDIA's major business risks?"** under *Try asking* | "A *narrative* question goes through RAG over the 10-K text. Every claim has a citation." Each source shows its full passage; click **📍 Open at this exact spot**: "SEC.gov opens scrolled to that exact sentence, highlighted. Or **📖 Read the full section** right here in the app." |
| 3 | Open **🔍 How this answer was made** | "The full trail: the route chosen, chunks retrieved, the model that answered, whether it came from the cache, and the number-guard result." |
| 4 | On Ask AI, click **"Compare Apple's revenue with Microsoft's"** | "A *numbers* question: the figures come from SEC XBRL data, not the AI. Python calculated the difference and the percentage. Note the warning that Apple's year ends in September and Microsoft's in June." |
| 5 | Click **"Explain Amazon's operating income"** | "*Both*: the exact figure is cited as [F], plus the explanation from the MD&A text." |
| 6 | **Company Dashboard** → pick a company | "KPIs, net margin calculated by Python, a 5-year trend, and insights written by Python, not the AI. Here gross profit says *not reported* because the company doesn't tag it." |
| 7 | **Compare** → *5-year trend* tab | "All five companies over five years, each in its brand colour. No AI on this page; it's all exact data." |
| 8 | **Upload & Analyze** → click **📗 Statements (XLSX)** → "How did revenue grow year by year?" | "For tables, the LLM only chooses an operation from a whitelist as JSON. Python validates it and runs it with Pandas. Here's the exact calculation and the plan." |
| 9 | Upload `samples/scanned_invoice.pdf` | "Scanned images have no text layer, so it refuses honestly rather than guessing." |
| 10 | If the interviewer has a file: **drag it into the upload zone** and ask their question | (this is the real test, so stay calm) |
| 11 | **How it works** page, then **http://127.0.0.1:8000/docs** | "The architecture on one page, and every API endpoint documented automatically from the Pydantic schemas." |

**If something goes wrong live:**

| Problem | What happens / what to say |
|---|---|
| Gemini slow or 503 | "The fallback chain switches models automatically." The answer badge shows which model answered |
| Quota used up | Demo questions come from the cache (⚡ badge). "Repeated questions are cached to save free-tier quota." |
| No internet | Ollama answers locally (slower). Numbers questions still show the exact table without the AI |
| The app shows "API not running" | Restart `run_demo.ps1`. Calmly explain the two-process architecture while it starts |

---

## 3. Follow one question through the system

> **"Compare Apple's revenue with Microsoft's"**

1. **Streamlit** sends `POST /chat {"question": ...}` through `api_client`.
2. **FastAPI** validates it with the Pydantic `ChatRequest`. The `/chat` route calls `chat_service.answer_chat()`.
3. **The question router** sees the metric "revenue" and no "explain/why", so the route is **numbers**. The companies detected are AAPL and MSFT.
4. **The financial service** loads `metrics.csv` (built from XBRL Company Facts), takes each company's latest original 10-K value, and ranks them. Pandas computes the difference ($147.00B) and % (44.30%). It adds the note that fiscal years end on different dates.
5. **The cache** is checked: is the same question already answered with the same data? If not, continue.
6. **The LLM** (Gemini 3.5 Flash Lite, with fallbacks) gets the FIGURES text and rules (no new calculations, state the periods) and writes a short explanation.
7. **The number guard** checks every number in the explanation against the figures and flags any it can't find.
8. **The response** (answer, route, financials table, model, cached) returns as JSON. Streamlit renders the table, summary, notes and SEC links.

For a **narrative** question, steps 3–4 become: detect the company, topic section and year → **embed the question** (384 numbers) → **ChromaDB** cosine search filtered by company and section → number the top chunks as sources → Gemini answers with `[n]` citations.

---

## 4. Concepts in one breath each

| Concept | Simple explanation |
|---|---|
| **LLM** | A model that predicts the next words. Great at language, but it doesn't know facts it wasn't given, and it can make them up (hallucination) |
| **RAG** | Retrieve relevant passages first, then let the LLM answer **only from them**. It's an open-book exam with page references |
| **Embedding** | Text turned into 384 numbers that capture its meaning. Similar meanings get similar numbers |
| **Cosine similarity** | How close two embeddings point. 1 = same meaning, about 0 = unrelated |
| **Chunking** | Cutting reports into ~800-character pieces on sentence boundaries with 150 characters of overlap, so search is precise and fits the model's 256-token limit |
| **ChromaDB** | A vector database: stores the chunks, their embeddings and metadata, and finds the nearest ones, with filters like `ticker = AAPL` |
| **Metadata filter** | Exact filtering (company, section, year) combined with meaning search |
| **Temperature** | Randomness. 0.2 keeps answers factual and consistent |
| **System vs user prompt** | The permanent rules vs this question plus its sources |
| **Prompt injection** | A document containing instructions like "ignore your rules". We tell the model the sources are data, and we never execute AI-generated code |
| **XBRL** | Machine-readable tags in SEC filings, e.g. Apple's `NetIncomeLoss = 132,175,000,000 USD` for FY2026 |
| **Pydantic** | Data validation: bad input is rejected with 422 before any code runs |

---

## 5. Likely questions, and good answers

**RAG and AI**

1. *Why RAG instead of fine-tuning?* "The facts change every year and need citations. RAG uses the latest documents without retraining, shows its sources, and is free. Fine-tuning teaches style, not reliable facts."
2. *Why this embedding model?* "all-MiniLM-L6-v2 is small (about 90 MB), fast on a CPU, free and offline, with 384 dimensions. It's good enough for paragraph-level search. A bigger model could improve recall; that's a future improvement."
3. *Why 800-character chunks with overlap?* "The model reads about 256 tokens, roughly 1,000 characters, so longer text is silently cut. Sentence boundaries keep ideas whole, and the 150-character overlap protects ideas that sit on a cut."
4. *How do you stop hallucination?* "Four layers:
   - grounding rules in the prompt
   - citations, with our code checking that each cited source exists
   - **numbers from code, never from the LLM**
   - a **number guard** that flags any figure not found in the evidence.
   When the evidence is missing, it says so."
5. *How do comparisons stay fair?* "Retrieval runs **per company**, so one company can't fill all the top-k slots."
6. *What if the search returns irrelevant chunks?* "There's a relevance threshold (0.25). If nothing passes, we don't call the LLM at all; we answer 'not found'."

**Financial data**

7. *Why not let the LLM calculate the difference?* "LLMs are unreliable at arithmetic, and it can't be audited. Pandas is exact and testable. The LLM only explains."
8. *What traps did the SEC data have?*
   - Every 10-K repeats last year's numbers. Fix: keep each filing's own year.
   - 10-Ks contain quarterly figures. Fix: 350–380 day periods only.
   - Amendments. Fix: original 10-K only.
   - Companies switch tags. Fix: the best tag per year.
   - Missing tags. Fix: derive (and label it), or say "not reported".
   - A stale 2009 Amazon gross-profit value. Fix: treat anything over a year out of date as not reported.
9. *Can you compare Apple FY2026 and Microsoft FY2026?* "Not as the same period: Apple's year ends in September, Microsoft's in June. The system labels each period and warns."

**Uploads and security**

10. *How do you handle an uploaded Excel file?*
    - Validate the type, size and real file signature, and refuse macro files.
    - Clean the data: find the real header row, convert `$1,234` and `(500)`, and reshape wide year columns into long format.
    - The LLM fills in a whitelisted JSON plan; Python validates it and runs it with Pandas.
11. *Why not let the LLM write Pandas code?* "A malicious file could inject instructions and turn into code execution on my server. A fixed menu of operations removes that risk."
12. *What about scanned PDFs?* "There's no text layer, so we detect fewer than 30 characters per page and refuse honestly. OCR is a future improvement."

**Engineering**

13. *Why FastAPI and Streamlit as separate apps?* "Separation of concerns: the API can serve any client, it's testable on its own, and the UI stays a thin client."
14. *Why `def` routes and not `async def`?* "The work is blocking (embeddings, LLM calls). Plain `def` runs in a thread pool, so one slow request doesn't freeze the server."
15. *How do you handle the free-tier limits?*
    - The first model allowed only 20 requests a day. I checked the real limits and switched to Flash Lite, which allows 500 a day.
    - I built a fallback chain across models with separate quotas, plus an answer cache and a local Ollama model. Overload errors move to the next model instead of retrying the same one.
16. *How did you test without spending quota?*
    - 187 pytest tests with fakes for the LLM, embeddings and network.
    - TestClient for the API; Streamlit AppTest for the UI.
    - Live checks were run separately and verified against the real filings.
17. *What would you change for production?*
    - Authentication and per-user storage
    - Docker
    - A managed vector database
    - Hybrid search with re-ranking
    - Monitoring, and a paid LLM tier with rate limiting
18. *What was the hardest bug?* Pick one story from section 6.

---

## 6. Engineering stories (real bugs found and fixed)

Interviewers love these, so tell 2 or 3:

1. **"The run passed, but the data was wrong."** Alphabet writes `ITEM 1A.RISK FACTORS` with no space, so its Risk Factors section came out as **27 characters**. Fixing the heading pattern brought it to about 85,000. Microsoft repeats an `Item 1A` header on every page, which cut its sections into pages. *Lesson: check sizes and read samples, not just "no errors".*
2. **The quota wall.** The first Gemini model allowed only 20 requests a day, and retries counted too. I read the real limits in AI Studio and built the Quota Shield. During testing, Google returned "503 overloaded" and the fallback switched models by itself.
3. **The request that never came back.** One Gemini request hung with no reply. I added a 120-second timeout, so a stuck call becomes a clear error and the fallback chain can move on.
4. **The AI did a sum.** It wrote "$42.5 million", a number that wasn't in the document. *Lesson: a prompt rule is a request, not a guarantee.* I added the number guard in code.
5. **`KeyError` is a `LookupError`.** Mapping LookupError to 404 would have turned real crashes into harmless-looking 404s. I used a dedicated `UnknownCompany` error.
6. **Amazon's 2009 gross profit** was shown next to Apple's 2026 value. Amazon tagged it only once, 16 years earlier, so stale values are now "not reported".
7. **Dollar signs broke the chat.** Streamlit reads text between two `$` signs as a LaTeX formula, so every `$` is now escaped.
8. **"What is Tesla's revenue?"** compared the 5 supported companies, because the word "revenue" triggered the numbers route. Questions that name no supported company and aren't rankings now go to RAG, which says honestly that Tesla isn't covered.

---

## 7. Numbers worth remembering

| Fact | Value |
|---|---|
| Companies / reports | 5 companies × 2 latest 10-Ks = 10 reports |
| SEC chunks in ChromaDB | 4,593 |
| Embedding size | 384 dimensions (all-MiniLM-L6-v2) |
| Chunk size / overlap | 800 / 150 characters |
| Automated tests | 187 |
| Main model free limit | gemini-3.5-flash-lite: 500 requests/day, 15/minute |
| Apple revenue FY2026 | **$478.83B** (period ending 26 Sep 2026); same in the 10-K and XBRL |
| Highest revenue (latest FY) | Amazon $716.92B (FY2025) |
| Highest net income (latest FY) | Microsoft $133.75B (FY2026) |
| Apple vs Microsoft revenue | Apple $147.00B higher (44.30%) |

---

## 8. Honest limitations (say them before they're found)

- 5 companies and 2 years of 10-Ks. Adding more means changing one file and re-running ingestion.
- A keyword router: simple and predictable, but it can miss unusual phrasings.
- No OCR; one table per upload question.
- Free-tier LLM: daily limits, and inputs may be used for training, so only public or sample data.
- Fiscal-year comparisons aren't the same calendar period. That's clearly labelled.

> **Closing line:** "I focused on making every answer verifiable: citations for text, exact Python figures for numbers, and honest refusals when the data isn't there."
