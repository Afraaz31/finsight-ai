"""Level 2, step 2: embed every chunk and store it in ChromaDB.

Run from the project root:  python -m ingestion.build_vectorstore
Add --rebuild to delete the collection and build it again from scratch.
"""
import argparse
import json
import logging
import time

from backend.config import SEC_COLLECTION
from backend.services.embedding_service import embed_texts
from backend.services.retrieval_service import get_client, get_or_create_collection
from ingestion.chunk_documents import CHUNKS_PATH

log = logging.getLogger(__name__)

BATCH_SIZE = 256   # chunks embedded and saved per round


def load_chunks() -> list[dict]:
    if not CHUNKS_PATH.exists():
        raise SystemExit("No chunks file. Run first:  python -m ingestion.chunk_documents")
    with CHUNKS_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed chunks and store them in ChromaDB.")
    parser.add_argument("--rebuild", action="store_true", help="delete the collection first")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # hide one log line per model-file request

    chunks = load_chunks()
    if args.rebuild:
        try:
            get_client().delete_collection(SEC_COLLECTION)
            log.info("Deleted old collection '%s'", SEC_COLLECTION)
        except Exception:
            pass  # it did not exist yet
    collection = get_or_create_collection(SEC_COLLECTION)

    if collection.count() == len(chunks) and not args.rebuild:
        print(f"Collection '{SEC_COLLECTION}' already has all {len(chunks)} chunks. "
              "Nothing to do (use --rebuild to start over).")
        return

    log.info("Embedding %d chunks into '%s' ...", len(chunks), SEC_COLLECTION)
    start = time.time()
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        collection.upsert(            # upsert = insert, or overwrite if the id already exists
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
            embeddings=embed_texts([c["text"] for c in batch]),
        )
        log.info("  %d / %d", min(i + BATCH_SIZE, len(chunks)), len(chunks))

    print(f"\nDone in {time.time() - start:.0f} s. "
          f"Collection '{SEC_COLLECTION}' now holds {collection.count()} chunks.")


if __name__ == "__main__":
    main()
