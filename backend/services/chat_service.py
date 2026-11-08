"""Level 7: the hybrid chat. Routes each SEC question to the right engine.

    narrative -> rag_service.answer_question (unchanged Level 3 pipeline)
    numbers   -> financial_service.compare (exact figures, Python maths) -> LLM explains them
    both      -> exact figures + retrieved 10-K text -> one LLM answer with [F] and [n] citations

If the LLM is unavailable on a numbers question, the exact figures are still returned with a
plain summary written by Python, so the user always gets the facts.
"""
import logging

from backend.companies import COMPANIES
from backend.config import METRICS_PATH
from backend.services import cache_service, number_guard
from backend.services.financial_service import compare, figures_text, year_over_year
from backend.services.llm_service import LLMError, generate_answer
from backend.services.question_router import route
from backend.services.rag_service import (RETRIEVAL_VERSION, SYSTEM_PROMPT, YEAR, answer_question,
                                          build_context, detect_companies, format_sources, retrieve)

log = logging.getLogger(__name__)

FIGURES_PROMPT = """You are FinSight AI. Explain financial figures that Python has already retrieved \
from official SEC XBRL data and compared.

Rules:
1. Use the numbers in FIGURES exactly as given (you may use the short form like $478.83B). Do not \
calculate anything new: no new sums, differences or percentages.
2. Always state each company's fiscal year and period end. If the periods differ, say so clearly.
3. Mention any notes (e.g. derived values, companies that don't report the metric).
4. No investment advice. Plain English for a non-expert, under about 150 words.
5. If the figures are ONE company's different years, describe the change (rose or fell, by how much, \
using the given difference and percentage). If asked whether a year was "good" or "bad", say what the \
figures show and label any judgement as interpretation, e.g. "This suggests..."."""

FIGURES_RULE = """
10. VERIFIED FIGURES were retrieved from SEC XBRL data and calculated by Python. Quote them exactly \
and cite them as [F]. Never calculate new figures from them. If they compare one company's years, \
start the answer with that change, then explain it with the 10-K text. If the question asks whether the \
result was good or bad (better, worse...), answer that directly, based on the figures, and label it as \
interpretation, e.g. "This suggests..."."""


# Words that mean "compare / rank the companies" when no company is named.
ALL_COMPANY_WORDS = ["which company", "which companies", "all companies", "all five", "all 5", "companies",
                     "highest", "lowest", "largest", "smallest", "most", "least", "rank", "compare",
                     "comparison", "versus", " vs"]


def _companies_for(question: str, ticker: str | None) -> list[str] | None:
    """Companies for a numbers question, or None if the question names no supported company.

    "Which company had the highest revenue?" -> all 5 (a ranking question)
    "What is Tesla's revenue?"               -> None  (not a supported company: let RAG say so)
    """
    if ticker:
        return [ticker.upper()]
    found = detect_companies(question)
    if found:
        return found
    q = question.lower()
    if any(word in q for word in ALL_COMPANY_WORDS):
        return list(COMPANIES)
    return None


def _fallback_summary(comparisons: list[dict]) -> str:
    """Plain summary written by Python when no LLM is available."""
    parts = ["The AI explanation is unavailable right now, but here are the exact SEC figures:"]
    for comp in comparisons:
        parts.append(comp["summary"] or "; ".join(
            f"{r['company']}: {r['value_display']} (FY{r['fiscal_year']})" for r in comp["rows"]))
        parts.extend(comp["notes"])
    return "\n\n".join(parts)


def answer_chat(question: str, ticker: str | None = None, use_cache: bool = True) -> dict:
    """Main entry point for SEC questions (used by POST /chat)."""
    question = question.strip()
    if not question:
        raise ValueError("Question is empty.")
    decision = route(question)

    if decision["route"] == "narrative":
        return {**answer_question(question, ticker=ticker, use_cache=use_cache),
                "route": "narrative", "financials": None}

    tickers = _companies_for(question, ticker)
    if tickers is None:   # a metric, but no supported company (e.g. Tesla) -> honest RAG answer
        return {**answer_question(question, ticker=ticker, use_cache=use_cache),
                "route": "narrative", "financials": None}
    if len(tickers) == 1:   # one company -> compare its own years ("was 2026 better than 2025?")
        years = sorted({int(y) for y in YEAR.findall(question)}) or None
        comparisons = [year_over_year(tickers[0], metric, years) for metric in decision["metrics"]]
    else:
        comparisons = [compare(tickers, metric) for metric in decision["metrics"]]
    figures = figures_text(comparisons)

    data_version = METRICS_PATH.stat().st_mtime if METRICS_PATH.exists() else 0
    key = cache_service.make_key(cache_service.normalize(question), ",".join(tickers), decision["route"],
                                 FIGURES_PROMPT, SYSTEM_PROMPT, FIGURES_RULE, RETRIEVAL_VERSION, data_version)
    if use_cache and (cached := cache_service.get(key)):
        return {**cached, "cached": True}

    sources, hits = [], []
    try:
        if decision["route"] == "numbers":
            answer, model = generate_answer(FIGURES_PROMPT, f"FIGURES:\n{figures}\n\nQUESTION: {question}")
            evidence = figures
        else:   # both: exact figures + the 10-K text that explains them
            hits = retrieve(question, tickers if len(tickers) < len(COMPANIES) else [])
            context = build_context(hits)
            prompt = (f"SOURCES:\n\n{context}\n\nVERIFIED FIGURES [F]:\n{figures}\n\n---\n"
                      f"QUESTION: {question}\n\nAnswer using only the sources and figures above.")
            answer, model = generate_answer(SYSTEM_PROMPT + FIGURES_RULE, prompt)
            evidence = context + "\n" + figures
    except LLMError as exc:
        log.warning("LLM unavailable for a numbers question, returning figures only: %s", exc)
        return {"answer": _fallback_summary(comparisons), "sources": [], "companies": tickers,
                "used_llm": False, "model": None, "cached": False, "retrieved_chunks": 0,
                "unverified_numbers": [], "route": decision["route"], "financials": comparisons}

    missing = number_guard.unverified_numbers(answer, evidence + "\n" + question)
    answer = number_guard.add_warning(answer, missing)
    if hits:
        sources = format_sources(hits, answer)
    result = {"answer": answer, "sources": sources, "companies": tickers, "used_llm": True,
              "model": model, "cached": False, "retrieved_chunks": len(hits),
              "unverified_numbers": missing, "route": decision["route"], "financials": comparisons}
    if use_cache and not model.startswith("ollama:"):
        cache_service.put(key, question, result)
    return result
