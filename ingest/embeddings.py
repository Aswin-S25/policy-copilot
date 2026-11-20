import threading
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_infra_settings

EMBEDDING_MODEL = get_infra_settings().embedding_model

# The warm-up thread and the first request may load concurrently;
# lru_cache alone would let both build the model.
_load_lock = threading.Lock()


@lru_cache
def _load_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


def get_embedding_model() -> SentenceTransformer:
    with _load_lock:
        return _load_model()


def embedding_model_loaded() -> bool:
    return _load_model.cache_info().currsize > 0


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()

    embedding = model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    
    
    model = get_embedding_model()
    
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False
    )
    
    return embeddings.tolist()

