"""Pre-warm the demo: answer each demo question once so it is saved in the answer cache.

Run AFTER the last code or prompt change (the cache key includes the prompts):
    python -m scripts.prewarm

During the demo these questions then answer instantly, even if Gemini is slow or out of quota.
New questions still go to Gemini live.
"""
import logging
import time

from backend.agents import orchestrator
from backend.services.chat_service import answer_chat
from backend.services.llm_service import LLMError
from backend.services.upload_service import UploadError, list_uploads

DEMO_QUESTIONS = [
    "What are NVIDIA's major business risks?",
    "What was Apple's revenue in its latest reported fiscal year?",
    "Compare Apple's revenue with Microsoft's",
    "Which company reported the highest net income?",
    "Compare the financial performance of all five companies",
    "Explain Amazon's operating income",
    "Explain the business segments of Alphabet",
    "Summarize the management discussion in Apple's annual report",
    "What are Microsoft's major business risks?",
    "What is Tesla's revenue?",
    "Audit report of Apple",                           # Level 11: the 10-section Company Report
    "Audit report of Microsoft",                       # Level 11: the 10-section Company Report
    "Audit report of Amazon",                          # Level 11: the 10-section Company Report
    "Audit report of Alphabet",                        # Level 11: the 10-section Company Report
    "Audit report of NVIDIA",                          # Level 11: the 10-section Company Report
    "Was Apple's 2026 profit better than 2025?",            # Level 10: one company, year over year
]

# Level 12: Upload & Analyze questions, asked with NOTHING ticked (the Orchestrator sees every uploaded file).
# Upload the four samples first (Annual report PDF, Board memo TXT, Financials CSV, Statements XLSX).
UPLOAD_DEMO_QUESTIONS = [
    "What is the net profit margin for each year?",                             # Spreadsheet Agent
    "What are the main risks mentioned?",                                       # Document Agent
    "Does the revenue in the spreadsheet match the annual report?",             # both agents
    "What were the biggest expenses in 2025?",                                  # picks the Expenses sheet
    "Calculate revenue growth and explain what the report says caused it",     # both agents
]


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    new = cached = failed = 0
    for question in DEMO_QUESTIONS:
        start = time.time()
        try:
            result = answer_chat(question, use_cache=True)
        except LLMError as exc:
            failed += 1
            print(f"[FAIL]   {question}\n         {exc}")
            continue
        if result.get("cached"):
            cached += 1
            status = "cached"
        else:
            new += 1
            status = "new   "
        warn = f"  (unverified: {result['unverified_numbers']})" if result.get("unverified_numbers") else ""
        print(f"[{status}] {question}  ->  route={result.get('route')}  model={result.get('model')}  "
              f"{time.time() - start:.1f}s{warn}")

    uploads = list_uploads()
    print(f"\nUpload & Analyze ({len(uploads)} uploaded file(s), nothing ticked):")
    for question in UPLOAD_DEMO_QUESTIONS if uploads else []:
        start = time.time()
        try:
            result = orchestrator.ask(question, use_cache=True)
        except (LLMError, UploadError) as exc:
            failed += 1
            print(f"[FAIL]   {question}\n         {exc}")
            continue
        new, cached = (new, cached + 1) if result.get("cached") else (new + 1, cached)
        trace = result["orchestrator"]
        warn = f"  (unverified: {result['unverified_numbers']})" if result.get("unverified_numbers") else ""
        print(f"[{'cached' if result.get('cached') else 'new   '}] {question}  ->  "
              f"{' + '.join(a['agent'] for a in trace['agents'])} ({trace['decided_by']})  "
              f"{time.time() - start:.1f}s{warn}")
    if not uploads:
        print("  (no uploads: upload the four samples on the Upload & Analyze page, then run this again)")
    print(f"\n{new} newly answered (SEC: ~1 Gemini request each, uploads: 2-4 each), {cached} already cached, {failed} failed.")
    if failed:
        print("Run again later for the failed ones (the cached ones cost nothing).")


if __name__ == "__main__":
    main()
