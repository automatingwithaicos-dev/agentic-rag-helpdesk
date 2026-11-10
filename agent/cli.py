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
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first. The agent needs a model to decide which tools to call.")

    tools = HelpDeskTools(VectorIndex.load(args.index), args.directory)

    if args.command == "ask":
        _print_result(run_agent(args.question, tools, max_steps=args.max_steps), args.trace)
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
            _print_result(run_agent(question, tools, max_steps=args.max_steps), args.trace)
    if tools.tickets:
        print(f"\nTickets created this session: {', '.join(t['id'] for t in tools.tickets)}")


if __name__ == "__main__":
    main()
