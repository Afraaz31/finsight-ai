"""Pre-warm the demo: answer each demo question once so it is saved in the answer cache.

Run AFTER the last code or prompt change (the cache key includes the prompts):
    python -m scripts.prewarm

During the demo these questions then answer instantly, even if Gemini is slow or out of quota.
New questions still go to Gemini live.
"""
import logging
import time

from backend.services.chat_service import answer_chat
from backend.services.llm_service import LLMError

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
    print(f"\n{new} newly answered (about {new} Gemini requests), {cached} already cached, {failed} failed.")
    if failed:
        print("Run again later for the failed ones (the cached ones cost nothing).")


if __name__ == "__main__":
    main()
