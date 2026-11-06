"""Level 2 tests: chunking logic and search filters (no model or internet needed)."""
from backend.services.retrieval_service import build_filter
from ingestion.chunk_documents import chunk_document, chunk_text


def _sample_text() -> str:
    paragraph = " ".join(f"Sentence number {i} talks about supply chain risk." for i in range(40))
    return paragraph + "\n" + paragraph


def test_chunks_never_exceed_size():
    chunks = chunk_text(_sample_text(), size=300, overlap=80)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_neighbouring_chunks_overlap():
    chunks = chunk_text(_sample_text(), size=300, overlap=80)
    last_sentence_of_first = chunks[0].split(". ")[-1].rstrip(".")
    assert last_sentence_of_first in chunks[1]


def test_no_sentence_is_lost():
    text = _sample_text()
    joined = " ".join(chunk_text(text, size=300, overlap=80))
    for i in range(40):
        assert f"Sentence number {i} " in joined


def test_very_long_sentence_is_hard_cut():
    chunks = chunk_text("x" * 1000, size=300, overlap=50)
    assert all(len(c) <= 300 for c in chunks)
    assert sum(len(c) for c in chunks) >= 1000


def test_chunk_document_ids_metadata_and_skips():
    doc = {
        "company": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193", "fiscal_year": 2026,
        "report_date": "2026-09-26", "filing_date": "2026-11-03",
        "accession_number": "0000320193-26-000026", "document_url": "https://www.sec.gov/x.htm",
        "sections": [
            {"section_id": "COVER", "section": "Cover Page", "text": "cover " * 200},
            {"section_id": "6", "section": "Item 6. [Reserved]", "text": "Item 6. [Reserved]"},
            {"section_id": "1A", "section": "Item 1A. Risk Factors", "text": _sample_text()},
        ],
    }
    chunks = chunk_document(doc)
    assert chunks, "expected chunks from Item 1A"
    assert all(c["metadata"]["section_id"] == "1A" for c in chunks)   # COVER and tiny Item 6 skipped
    assert chunks[0]["id"] == "AAPL_FY2026_1A_0000"
    assert chunks[0]["text"].startswith("Apple Inc. | FY2026 Form 10-K | Item 1A. Risk Factors\n")
    assert chunks[0]["metadata"]["document_url"] == "https://www.sec.gov/x.htm"
    assert len({c["id"] for c in chunks}) == len(chunks)               # ids are unique


def test_build_filter_formats():
    assert build_filter() is None
    assert build_filter(ticker="aapl") == {"ticker": "AAPL"}
    assert build_filter(ticker="AAPL", section_id="1a") == {
        "$and": [{"ticker": "AAPL"}, {"section_id": "1A"}]
    }
