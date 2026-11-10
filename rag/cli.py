"""Command line interface.

    python -m rag ingest              build the index from data/kb
    python -m rag ask "question"      answer one question
    python -m rag chat                ask questions interactively
"""

from __future__ import annotations

import argparse

from .answer import answer
from .loader import load_documents
from .store import VectorIndex

DEFAULT_DOCS = "data/kb"
DEFAULT_INDEX = "index"


def cmd_ingest(args: argparse.Namespace) -> None:
    chunks = load_documents(args.docs, args.max_words, args.overlap)
    index = VectorIndex.build(chunks, backend=args.backend)
    index.save(args.index)
    sources = len({c.source for c in chunks})
    print(f"Indexed {len(chunks)} chunks from {sources} documents with '{args.backend}' into {args.index}/")


def _ask(index: VectorIndex, question: str, args: argparse.Namespace) -> None:
    k, show_sources = args.k, args.sources
    results = index.search(question, k=k)
    print(answer(question, results, backend=index.embedder.name,
                 provider=args.provider, model=args.model, base_url=args.base_url))
    if show_sources:
        print("\nSources:")
        for chunk, score in results:
            print(f"  - {chunk.title} ({chunk.source}) score {score:.2f}")


def cmd_ask(args: argparse.Namespace) -> None:
    _ask(VectorIndex.load(args.index), args.question, args)


def cmd_chat(args: argparse.Namespace) -> None:
    index = VectorIndex.load(args.index)
    print("IT Help Desk Assistant. Type a question, or 'quit' to exit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"quit", "exit", "q"}:
            break
        if question:
            _ask(index, question, args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rag", description="Retrieval-augmented help desk assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Embed documents and build the index")
    ingest.add_argument("--docs", default=DEFAULT_DOCS)
    ingest.add_argument("--index", default=DEFAULT_INDEX)
    ingest.add_argument("--backend", choices=["fastembed", "tfidf"], default="fastembed")
    ingest.add_argument("--max-words", type=int, default=120)
    ingest.add_argument("--overlap", type=int, default=30)
    ingest.set_defaults(func=cmd_ingest)

    for name, func, helptext in (("ask", cmd_ask, "Answer one question"), ("chat", cmd_chat, "Interactive mode")):
        p = sub.add_parser(name, help=helptext)
        if name == "ask":
            p.add_argument("question")
        p.add_argument("--index", default=DEFAULT_INDEX)
        p.add_argument("-k", type=int, default=3, help="Number of passages to retrieve")
        p.add_argument("--sources", action="store_true", help="Show retrieved sources and scores")
        p.add_argument("--provider", choices=["local", "claude", "none"],
                       help="local = Ollama/LM Studio, claude = Claude API, none = show passages only")
        p.add_argument("--model", help="Model name, for example qwen2.5:7b for Ollama")
        p.add_argument("--base-url", help="Local server URL (default Ollama: http://localhost:11434/v1)")
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
