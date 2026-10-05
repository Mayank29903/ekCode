import os
import threading

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_lock = threading.Lock()
_model = None


def model_name() -> str:
    return os.getenv("EMBED_MODEL", DEFAULT_MODEL)


def model():
    """Loaded once per process; the lock stops two first requests (API threads) loading it twice."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(model_name(), device="cpu")
    return _model


def embed(texts: list[str], batch_size: int = 128) -> np.ndarray:
    """Unit-length vectors, so a dot product is the cosine similarity."""
    if not texts:
        return np.zeros((0, model().get_sentence_embedding_dimension()), dtype=np.float32)
    return model().encode([t or " " for t in texts], batch_size=batch_size, normalize_embeddings=True,
                          show_progress_bar=False)
