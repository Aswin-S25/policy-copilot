"""Text embeddings: one model, two interchangeable runtimes.

The model is BAAI/bge-small-en-v1.5: CLS-token pooling, L2-normalized,
384 dimensions, 512-token input. Stored chunk vectors and query vectors
must come from the same model, so only the runtime is configurable
(POLICY_EMBEDDING_BACKEND):

  sentence-transformers  PyTorch. Default: local development, ingestion, eval.
  onnx                   onnxruntime + tokenizers, running the model's
                         official ONNX export. No PyTorch: a fraction of the
                         memory, for the 512 MB free-tier deployment.

Each backend's library is imported only when that backend is used, so the
deployment image doesn't need PyTorch installed at all.
"""
import os
import threading
from functools import lru_cache

import numpy as np

from app.core.config import get_infra_settings

_settings = get_infra_settings()
EMBEDDING_MODEL = _settings.embedding_model
MAX_TOKENS = 512

# The warm-up thread and the first request may load concurrently;
# lru_cache alone would let both build the model.
_load_lock = threading.Lock()


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        return self._model.encode(
            texts, normalize_embeddings=True, batch_size=batch_size, show_progress_bar=False,
        )


class _OnnxEmbedder:
    """The same model through onnxruntime: tokenize, run the encoder, take
    the [CLS] vector, L2-normalize (what the sentence-transformers pipeline
    for this model does: 1_Pooling/config.json sets CLS pooling)."""

    def __init__(self, model_dir: str):
        import onnxruntime
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = onnxruntime.InferenceSession(
            os.path.join(model_dir, "model.onnx"), options, providers=["CPUExecutionProvider"],
        )
        self._inputs = {i.name for i in self._session.get_inputs()}

    def encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        vectors = []
        for start in range(0, len(texts), batch_size):
            encodings = self._tokenizer.encode_batch(texts[start:start + batch_size])
            ids = np.array([e.ids for e in encodings], dtype=np.int64)
            feeds = {
                "input_ids": ids,
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            }
            if "token_type_ids" in self._inputs:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feeds)[0]  # (batch, tokens, 384)
            cls = hidden[:, 0, :]
            vectors.append(cls / np.linalg.norm(cls, axis=1, keepdims=True))
        return np.vstack(vectors)


@lru_cache
def _load_model():
    if _settings.embedding_backend == "onnx":
        return _OnnxEmbedder(_settings.embedding_onnx_dir)
    return _SentenceTransformerEmbedder(EMBEDDING_MODEL)


def get_embedding_model():
    with _load_lock:
        return _load_model()


def embedding_model_loaded() -> bool:
    return _load_model.cache_info().currsize > 0


def embed_text(text: str) -> list[float]:
    return get_embedding_model().encode([text], batch_size=1)[0].tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return get_embedding_model().encode(texts, batch_size=32).tolist()
