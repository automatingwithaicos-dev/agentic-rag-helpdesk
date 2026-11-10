"""Load markdown documents and split them into overlapping chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    """A piece of a source document that gets embedded and searched."""

    id: str
    source: str
    title: str
    text: str


def _title_of(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def split_text(text: str, max_words: int = 120, overlap: int = 30) -> list[str]:
    """Split text into chunks of roughly max_words, keeping paragraphs together.

    Overlap carries the tail of one chunk into the next so an answer that
    spans a boundary is still found.
    """
    if overlap >= max_words:
        raise ValueError("overlap must be smaller than max_words")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []

    for para in paragraphs:
        words = para.split()
        if current and len(current) + len(words) > max_words:
            chunks.append(" ".join(current))
            current = current[-overlap:] if overlap else []
        current.extend(words)
        while len(current) > max_words:
            chunks.append(" ".join(current[:max_words]))
            current = current[max_words - overlap:]

    if current:
        chunks.append(" ".join(current))
    return chunks


def load_documents(folder: str | Path, max_words: int = 120, overlap: int = 30) -> list[Chunk]:
    """Read every .md and .txt file in a folder and return its chunks."""
    folder = Path(folder)
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in {".md", ".txt"})
    if not files:
        raise FileNotFoundError(f"No .md or .txt files found in {folder}")

    chunks: list[Chunk] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        title = _title_of(text, path.stem.replace("-", " ").title())
        for i, piece in enumerate(split_text(text, max_words, overlap)):
            chunks.append(Chunk(id=f"{path.stem}#{i}", source=path.name, title=title, text=piece))
    return chunks
