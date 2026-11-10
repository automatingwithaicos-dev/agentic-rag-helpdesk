"""Turn retrieved chunks into an answer.

If ANTHROPIC_API_KEY is set, Claude writes the answer using only the
retrieved context and cites its sources. Without a key, the tool falls
back to showing the best-matching passages, so it still works offline.
"""

from __future__ import annotations

import os

from .loader import Chunk

# Below these similarity scores, the knowledge base probably doesn't cover the question.
# Dense embeddings score unrelated text higher than tfidf does, so each backend has its own floor.
MIN_SCORES = {"tfidf": 0.15, "fastembed": 0.55}

SYSTEM_PROMPT = (
    "You are an IT help desk assistant. Answer the user's question using ONLY the "
    "numbered context passages. Give clear steps when the answer is a procedure. "
    "Cite passages like [1] or [2]. If the context does not contain the answer, "
    "say you don't know and suggest opening a ticket for Tier 2."
)


def build_prompt(question: str, results: list[tuple[Chunk, float]]) -> str:
    context = "\n\n".join(
        f"[{i}] ({chunk.title}, {chunk.source})\n{chunk.text}"
        for i, (chunk, _score) in enumerate(results, start=1)
    )
    return f"Context:\n{context}\n\nQuestion: {question}"


def extractive_answer(question: str, results: list[tuple[Chunk, float]], min_score: float = 0.15) -> str:
    if not results or results[0][1] < min_score:
        return "I couldn't find this in the knowledge base. Please open a ticket for Tier 2."
    lines = ["Best matching passages (set ANTHROPIC_API_KEY for a written answer):", ""]
    for i, (chunk, score) in enumerate(results, start=1):
        lines.append(f"[{i}] {chunk.title} ({chunk.source}, score {score:.2f})")
        lines.append(f"    {chunk.text}")
        lines.append("")
    return "\n".join(lines).rstrip()


def llm_answer(question: str, results: list[tuple[Chunk, float]], model: str | None = None) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model or os.environ.get("RAG_MODEL", "claude-haiku-5-5"),
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(question, results)}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def answer(question: str, results: list[tuple[Chunk, float]], backend: str = "tfidf") -> str:
    min_score = MIN_SCORES.get(backend, 0.15)
    if not results or results[0][1] < min_score:
        return extractive_answer(question, results, min_score)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return llm_answer(question, results)
    return extractive_answer(question, results, min_score)
