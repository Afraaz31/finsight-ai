"""Ask FinSight a question from the terminal.

python -m scripts.ask "What are Apple's main business risks?"
python -m scripts.ask "Explain the business segments" --ticker GOOGL
python -m scripts.ask "Summarize NVIDIA's annual report" --show-context
python -m scripts.ask "What are Apple's main risks?" --no-cache     (force a fresh answer)
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
                        help="also print exactly what was sent to the LLM")
    parser.add_argument("--no-cache", action="store_true", help="ignore saved answers")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    if args.show_context:
        tickers = [args.ticker.upper()] if args.ticker else detect_companies(args.question)
        print("=" * 30, "CONTEXT SENT TO THE LLM", "=" * 30)
        print(build_context(retrieve(args.question, tickers)) or "(no relevant chunks)")
        print("=" * 83, "\n")

    try:
        result = answer_question(args.question, ticker=args.ticker, use_cache=not args.no_cache)
    except LLMError as exc:
        raise SystemExit(f"\nLLM problem: {exc}")

    print(f"\nQ: {args.question}\n")
    print(result["answer"])
    if result["sources"]:
        print("\nSources (cited in the answer):")
        for s in result["sources"]:
            print(f"  [{s['number']}] {s['company']} FY{s['fiscal_year']} - {s['section']} "
                  f"(score {s['score']:.2f})\n       {s['document_url']}")

    if result["cached"]:
        print(f"\n(answer from cache - no quota used; originally by {result['model']})")
    elif result["used_llm"]:
        print(f"\n(answered by {result['model']} using {result['retrieved_chunks']} retrieved chunks)")
    else:
        print("\n(no LLM call: no relevant evidence was found)")


if __name__ == "__main__":
    main()
