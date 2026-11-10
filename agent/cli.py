"""Command line interface for the agent.

    python -m rag ingest                    build the knowledge base index first
    python -m agent ask "question" --trace  run the agent on one request
    python -m agent chat --trace            interactive mode
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from rag.store import VectorIndex

from .local_client import DEFAULT_LOCAL_MODEL, LocalModelClient
from .loop import run_agent
from .tools import DEFAULT_DIRECTORY, HelpDeskTools


def _print_result(result, trace: bool) -> None:
    if trace:
        for i, call in enumerate(result.tool_calls, start=1):
            args = json.dumps(call.arguments)
            preview = call.result if len(call.result) <= 300 else call.result[:300] + "..."
            print(f"  step {i}: {call.name}({args})")
            print(f"          -> {preview}")
        print()
    print(result.answer)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agent", description="Agentic RAG help desk assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("ask", "chat"):
        p = sub.add_parser(name)
        if name == "ask":
            p.add_argument("question")
        p.add_argument("--index", default="index")
        p.add_argument("--directory", default=str(DEFAULT_DIRECTORY))
        p.add_argument("--max-steps", type=int, default=8)
        p.add_argument("--trace", action="store_true", help="Show every tool call the agent makes")
        p.add_argument("--provider", choices=["local", "claude"], default=os.environ.get("AGENT_PROVIDER", "local"),
                       help="local = Ollama/LM Studio on your machine (default), claude = Claude API")
        p.add_argument("--model", help="Model name, for example qwen2.5:7b for Ollama")
        p.add_argument("--base-url", help="Local server URL (default Ollama: http://localhost:11434/v1)")
    args = parser.parse_args(argv)

    if args.provider == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Set ANTHROPIC_API_KEY to use --provider claude, or use --provider local.")
        client, model = None, args.model
    else:
        client = LocalModelClient(base_url=args.base_url)
        model = args.model or os.environ.get("LOCAL_MODEL", DEFAULT_LOCAL_MODEL)

    tools = HelpDeskTools(VectorIndex.load(args.index), args.directory)

    def run(question: str):
        try:
            return run_agent(question, tools, client=client, model=model, max_steps=args.max_steps)
        except Exception as exc:  # most often the local server isn't running
            if args.provider == "local" and "Connection" in type(exc).__name__:
                url = args.base_url or os.environ.get("LOCAL_BASE_URL", "http://localhost:11434/v1")
                sys.exit(f"Couldn't reach a local model server at {url}.\n"
                         f"Start Ollama (ollama serve) and pull a tool-calling model (ollama pull {model}),\n"
                         "or point --base-url at LM Studio (http://localhost:1234/v1).")
            raise

    if args.command == "ask":
        _print_result(run(args.question), args.trace)
        return

    print("Help Desk Agent. Describe the issue, or type 'quit' to exit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"quit", "exit", "q"}:
            break
        if question:
            _print_result(run(question), args.trace)
    if tools.tickets:
        print(f"\nTickets created this session: {', '.join(t['id'] for t in tools.tickets)}")


if __name__ == "__main__":
    main()
