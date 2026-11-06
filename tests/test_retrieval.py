"""Level 2 tests that need the real vector store. Skipped until build_vectorstore has been run."""
import pytest

from backend.config import VECTORSTORE_DIR

pytestmark = pytest.mark.skipif(
    not (VECTORSTORE_DIR / "chroma.sqlite3").exists(),
    reason="vector store not built yet (python -m ingestion.build_vectorstore)",
)


def test_company_filter_returns_only_that_company():
    from backend.services.retrieval_service import search
    hits = search("supply chain disruptions", k=5, ticker="AAPL")
    assert len(hits) == 5
    assert all(h["metadata"]["ticker"] == "AAPL" for h in hits)


def test_results_are_sorted_best_first():
    from backend.services.retrieval_service import search
    scores = [h["score"] for h in search("cybersecurity threats", k=5)]
    assert scores == sorted(scores, reverse=True)


def test_section_filter():
    from backend.services.retrieval_service import search
    hits = search("competition", k=3, ticker="MSFT", section_id="1A")
    assert hits and all(h["metadata"]["section_id"] == "1A" for h in hits)
