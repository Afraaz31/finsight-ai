"""Try a semantic search yourself.

python -m scripts.search_test "problems getting parts from suppliers"
python -m scripts.search_test "how does the company make money" --ticker NVDA
python -m scripts.search_test "cybersecurity threats" --ticker MSFT --section 1A -k 3
"""
import argparse

from backend.services.retrieval_service import search

PREVIEW_CHARS = 350


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over the 10-K chunks.")
    parser.add_argument("question")
    parser.add_argument("--ticker", help="only this company, e.g. AAPL")
    parser.add_argument("--section", help="only this 10-K item, e.g. 1A or 7")
    parser.add_argument("--year", type=int, help="only this fiscal year, e.g. 2026")
    parser.add_argument("-k", type=int, default=5, help="number of results (default 5)")
    args = parser.parse_args()

    hits = search(args.question, k=args.k, ticker=args.ticker,
                  section_id=args.section, fiscal_year=args.year)
    print(f'\nQuestion: "{args.question}"   filters: ticker={args.ticker} '
          f"section={args.section} year={args.year}\n")
    if not hits:
        print("No results (are the filters too strict?)")
    for rank, hit in enumerate(hits, 1):
        m = hit["metadata"]
        body = hit["text"].split("\n", 1)[-1]   # drop the header line for the preview
        print(f"#{rank}  score {hit['score']:.3f}  |  {m['ticker']} FY{m['fiscal_year']}  |  {m['section']}")
        print(f"    {body[:PREVIEW_CHARS].replace(chr(10), ' ')}...")
        print(f"    source: {m['document_url']}\n")


if __name__ == "__main__":
    main()
