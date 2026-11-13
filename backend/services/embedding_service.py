"""Turns text into embeddings (lists of 384 numbers) with a local Sentence Transformers model.

The SAME model must embed both the stored chunks and the user's questions.
Different models produce numbers that cannot be compared.
"""
import logging

from backend.config import EMBEDDING_MODEL

log = logging.getLogger(__name__)

_model = None


def get_model():
    """Load the model once (first call takes a few seconds; first-ever call downloads ~90 MB)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # heavy import, only when needed
        log.info("Loading embedding model '%s' ...", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str], show_progress: bool = False) -> list[list[float]]:
    """Embed many texts. normalize_embeddings=True makes cosine similarity work correctly."""
    vectors = get_model().encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=show_progress
    )
    return vectors.tolist()


def embed_query(question: str) -> list[float]:
    """Embed one user question."""
    return embed_texts([question])[0]
