"""A small vector index: build it, save it to disk, load it, and search it."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .embedder import TfidfEmbedder, get_embedder
from .loader import Chunk


class VectorIndex:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, embedder):
        self.chunks = chunks
        self.vectors = vectors
        self.embedder = embedder

    @classmethod
    def build(cls, chunks: list[Chunk], backend: str = "fastembed") -> "VectorIndex":
        embedder = get_embedder(backend)
        texts = [f"{c.title}. {c.text}" for c in chunks]
        embedder.fit(texts)
        return cls(chunks, embedder.embed(texts), embedder)

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        """Return the k chunks most similar to the query (cosine similarity)."""
        query_vec = self.embedder.embed([query])[0]
        scores = self.vectors @ query_vec
        top = np.argsort(scores)[::-1][:k]
        return [(self.chunks[i], float(scores[i])) for i in top]

    def save(self, folder: str | Path) -> None:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "vectors.npy", self.vectors)
        meta = {
            "backend": self.embedder.name,
            "chunks": [asdict(c) for c in self.chunks],
        }
        if isinstance(self.embedder, TfidfEmbedder):
            meta["embedder_state"] = self.embedder.state()
        (folder / "index.json").write_text(json.dumps(meta), encoding="utf-8")

    @classmethod
    def load(cls, folder: str | Path) -> "VectorIndex":
        folder = Path(folder)
        meta_path = folder / "index.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No index in {folder}. Run the ingest command first.")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        chunks = [Chunk(**c) for c in meta["chunks"]]
        embedder = get_embedder(meta["backend"], meta.get("embedder_state"))
        return cls(chunks, np.load(folder / "vectors.npy"), embedder)
