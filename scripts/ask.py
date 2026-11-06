"""Ask FinSight a question from the terminal.

python -m scripts.ask "What are Apple's main business risks?"
python -m scripts.ask "Explain the business segments" --ticker GOOGL
python -m scripts.ask "Summarize NVIDIA's annual report" --show-context
"""
import argparse
import logging

from backend.services.llm_service import LLMError
from backend.services.rag_service import (answer_question, build_context, detect_companies,
                                          retrieve)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask FinSight AI a question.")
    parser.add_argument("question")
    parser.add_argument("--ticker", help="force one company, e.g. AAPL")
    parser.add_argument("--show-context", action="store_true",
                        help="also print exactly what was sent to Gemini")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    if args.show_context:
        tickers = [args.ticker.upper()] if args.ticker else detect_companies(args.question)
        print("=" * 30, "CONTEXT SENT TO GEMINI", "=" * 30)
        print(build_context(retrieve(args.question, tickers)) or "(no relevant chunks)")
        print("=" * 82, "\n")

    try:
        result = answer_question(args.question, ticker=args.ticker)
    except LLMError as exc:
        raise SystemExit(f"\nGemini problem: {exc}")

    print(f"\nQ: {args.question}\n")
    print(result["answer"])
    if result["sources"]:
        print("\nSources:")
        for s in result["sources"]:
            mark = "*" if s["cited"] else " "
            print(f" {mark}[{s['number']}] {s['company']} FY{s['fiscal_year']} - {s['section']} "
                  f"(score {s['score']:.2f})\n      {s['document_url']}")
        print("\n * = cited in the answer")
    if not result["used_llm"]:
        print("\n(Gemini was not called: no relevant evidence was found.)")


if __name__ == "__main__":
    main()
