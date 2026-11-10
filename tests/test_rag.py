"""Tests run with the tfidf backend so they need no model download or API key."""

from pathlib import Path

import pytest

from rag.answer import answer
from rag.loader import load_documents, split_text
from rag.store import VectorIndex

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


@pytest.fixture(scope="module")
def index():
    return VectorIndex.build(load_documents(KB), backend="tfidf")


def test_split_text_respects_size_and_overlap():
    text = " ".join(f"w{i}" for i in range(300))
    chunks = split_text(text, max_words=100, overlap=20)
    assert all(len(c.split()) <= 100 for c in chunks)
    assert chunks[0].split()[-20:] == chunks[1].split()[:20]


def test_split_text_rejects_bad_overlap():
    with pytest.raises(ValueError):
        split_text("a b c", max_words=10, overlap=10)


def test_loads_all_documents():
    sources = {c.source for c in load_documents(KB)}
    assert len(sources) == 6


@pytest.mark.parametrize(
    "question, expected_source",
    [
        ("How do I unlock a locked out account?", "password-reset.md"),
        ("VPN says server unreachable from a hotel", "vpn-troubleshooting.md"),
        ("User lost their phone and needs MFA set up again", "mfa-setup.md"),
        ("Laptop not compliant, BitLocker", "intune-enrollment.md"),
        ("Print jobs stuck in the queue", "printer-issues.md"),
        ("Offboarding steps for a user's last day", "onboarding-offboarding.md"),
    ],
)
def test_retrieves_right_document(index, question, expected_source):
    top_chunk, _score = index.search(question, k=1)[0]
    assert top_chunk.source == expected_source


def test_index_round_trip(index, tmp_path):
    index.save(tmp_path)
    loaded = VectorIndex.load(tmp_path)
    question = "How do I clear stuck print jobs?"
    assert loaded.search(question, k=1)[0][0].id == index.search(question, k=1)[0][0].id


def test_unrelated_question_is_not_answered(index, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    results = index.search("What is the capital of France?", k=3)
    assert "couldn't find" in answer("What is the capital of France?", results)
