"""Level 2, step 1: cut each processed 10-K section into small, overlapping chunks.

Run from the project root:  python -m ingestion.chunk_documents
"""
import json
import logging
import re

from backend.config import CHUNK_OVERLAP, CHUNK_SIZE, PROCESSED_DIR

log = logging.getLogger(__name__)

CHUNKS_PATH = PROCESSED_DIR / "chunks" / "sec_chunks.jsonl"
MIN_SECTION_CHARS = 300          # skip tiny sections like "Item 6. [Reserved]"
SKIP_SECTIONS = {"COVER"}        # cover page = address, checkboxes, table of contents

# A sentence ends at . ! or ? followed by a space and a capital letter, digit, quote or bracket.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


def _split_sentences(line: str, size: int) -> list[str]:
    """Split one paragraph into sentences; hard-cut any sentence longer than `size`."""
    pieces = []
    for sentence in SENTENCE_END.split(line):
        while len(sentence) > size:
            pieces.append(sentence[:size])
            sentence = sentence[size:]
        if sentence.strip():
            pieces.append(sentence.strip())
    return pieces


def _to_units(text: str, size: int) -> list[tuple[str, bool]]:
    """Text -> list of (sentence, starts_new_paragraph)."""
    units = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            for i, piece in enumerate(_split_sentences(line, size)):
                units.append((piece, i == 0))
    return units


def _join(units: list[tuple[str, bool]]) -> str:
    """Rebuild text: a new paragraph starts on a new line, sentences in a paragraph join with a space."""
    out = ""
    for piece, new_paragraph in units:
        if out:
            out += "\n" if new_paragraph else " "
        out += piece
    return out


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Pack whole sentences into chunks of at most `size` characters.

    Neighbouring chunks share up to `overlap` characters (the last sentence or two),
    so an idea that sits on a chunk boundary is not lost.
    """
    chunks, current = [], []
    for unit in _to_units(text, size):
        if current and len(_join(current + [unit])) > size:
            chunks.append(_join(current))
            # carry the trailing sentences (up to `overlap` chars) into the next chunk
            carry = []
            for prev in reversed(current):
                if len(_join([prev] + carry)) > overlap:
                    break
                carry.insert(0, prev)
            current = carry if len(_join(carry + [unit])) <= size else []
        current.append(unit)
    if current:
        chunks.append(_join(current))
    return chunks


def chunk_document(doc: dict) -> list[dict]:
    """Turn one processed 10-K (from Level 1) into chunk records with id, text and metadata."""
    fiscal_year = doc.get("fiscal_year") or 0
    records = []
    for section in doc["sections"]:
        if section["section_id"] in SKIP_SECTIONS or len(section["text"]) < MIN_SECTION_CHARS:
            continue
        header = f"{doc['company']} | FY{fiscal_year} Form 10-K | {section['section']}"
        for i, body in enumerate(chunk_text(section["text"])):
            records.append({
                "id": f"{doc['ticker']}_FY{fiscal_year}_{section['section_id']}_{i:04d}",
                # The header is glued to every chunk so the embedding "knows" whose text this is.
                "text": f"{header}\n{body}",
                "metadata": {
                    "source_type": "sec_10k",
                    "company": doc["company"],
                    "ticker": doc["ticker"],
                    "cik": doc["cik"],
                    "fiscal_year": fiscal_year,
                    "report_date": doc["report_date"],
                    "filing_date": doc["filing_date"],
                    "accession_number": doc["accession_number"],
                    "section_id": section["section_id"],
                    "section": section["section"],
                    "document_url": doc["document_url"],
                    "chunk_index": i,
                },
            })
    return records


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    files = sorted(PROCESSED_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No processed reports. Run first:  python -m ingestion.extract_documents")

    all_chunks = []
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        chunks = chunk_document(doc)
        avg = sum(len(c["text"]) for c in chunks) // max(len(chunks), 1)
        log.info("%-20s %5d chunks  (avg %d chars)", path.name, len(chunks), avg)
        all_chunks.extend(chunks)

    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"\n{len(all_chunks)} chunks written to {CHUNKS_PATH.relative_to(PROCESSED_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
