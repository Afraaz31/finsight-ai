"""Search ChromaDB by meaning. Used by the chatbot (Level 3) and for uploaded files (Level 4)."""
import logging

import chromadb
from chromadb.config import Settings

from backend.config import SEC_COLLECTION, VECTORSTORE_DIR
from backend.services.embedding_service import embed_query

log = logging.getLogger(__name__)

_client = None


def get_client():
    """One ChromaDB client that stores everything in the vectorstore/ folder on disk."""
    global _client
    if _client is None:
        VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(VECTORSTORE_DIR), settings=Settings(anonymized_telemetry=False)
        )
    return _client


def get_or_create_collection(name: str):
    """A collection is like a table. 'cosine' = compare vectors by the angle between them."""
    return get_client().get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def build_filter(ticker: str | None = None, section_id: str | None = None,
                 fiscal_year: int | None = None) -> dict | None:
    """Turn optional filters into ChromaDB's `where` format."""
    conditions = []
    if ticker:
        conditions.append({"ticker": ticker.upper()})
    if section_id:
        conditions.append({"section_id": section_id.upper()})
    if fiscal_year:
        conditions.append({"fiscal_year": int(fiscal_year)})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}   # ChromaDB needs $and when there is more than one condition


def search(question: str, k: int = 5, ticker: str | None = None, section_id: str | None = None,
           fiscal_year: int | None = None, collection_name: str = SEC_COLLECTION) -> list[dict]:
    """Return the k chunks whose meaning is closest to the question.

    Each result: {"id", "text", "metadata", "score"} where score is 0..1 (higher = more similar).
    """
    collection = get_or_create_collection(collection_name)
    if collection.count() == 0:
        raise RuntimeError(f"Collection '{collection_name}' is empty. "
                           "Run first:  python -m ingestion.build_vectorstore")

    result = collection.query(
        query_embeddings=[embed_query(question)],
        n_results=k,
        where=build_filter(ticker, section_id, fiscal_year),
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for chunk_id, text, meta, distance in zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        hits.append({"id": chunk_id, "text": text, "metadata": meta,
                     "score": round(1 - distance, 3)})   # cosine distance -> similarity
    return hits
