from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)

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

