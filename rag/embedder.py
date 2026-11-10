"""Embedding backends.

`fastembed` runs a real sentence-embedding model (BAAI/bge-small-en-v1.5)
locally on CPU, with no API key and no GPU. `tfidf` is a lightweight
fallback that needs no model download, which is handy for tests and
offline machines.
"""

from __future__ import annotations

import numpy as np


class Embedder:
    name = "base"

    def fit(self, texts: list[str]) -> None:
        """Prepare the embedder on the corpus (only needed for tfidf)."""

    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class FastEmbedEmbedder(Embedder):
    name = "fastembed"

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding  # imported lazily so tfidf works without it

        self.model_name = model
        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(list(self._model.embed(texts)), dtype=np.float32)
        return _normalize(vectors)


class TfidfEmbedder(Embedder):
    name = "tfidf"

    def __init__(self, vocabulary: dict | None = None, idf: list | None = None):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        if vocabulary is not None and idf is not None:
            self._vectorizer.vocabulary_ = {k: int(v) for k, v in vocabulary.items()}
            self._vectorizer.idf_ = np.array(idf)

    def fit(self, texts: list[str]) -> None:
        self._vectorizer.fit(texts)

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._vectorizer.transform(texts).toarray().astype(np.float32)
        return _normalize(vectors)

    def state(self) -> dict:
        return {
            "vocabulary": {k: int(v) for k, v in self._vectorizer.vocabulary_.items()},
            "idf": self._vectorizer.idf_.tolist(),
        }


def get_embedder(backend: str, state: dict | None = None) -> Embedder:
    if backend == "fastembed":
        return FastEmbedEmbedder()
    if backend == "tfidf":
        state = state or {}
        return TfidfEmbedder(state.get("vocabulary"), state.get("idf"))
    raise ValueError(f"Unknown embedding backend: {backend}")
