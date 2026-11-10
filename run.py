"""One script to set up and run the project. Works on Windows, Mac, and Linux.

    uv run run.py setup                 build the knowledge base index
    uv run run.py check                 test the connection to your model
    uv run run.py ask "question"        run the agent on one request
    uv run run.py chat                  talk to the agent interactively
    uv run run.py rag "question"        plain RAG answer, no tools (for comparison)

Settings live in config.ini. Edit that file instead of passing flags.
"""

from __future__ import annotations

import configparser
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.ini"
INDEX_DIR = ROOT / "index"


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    if not config.read(CONFIG_FILE, encoding="utf-8"):
        sys.exit(f"Missing {CONFIG_FILE.name}. It should sit next to run.py.")
    return config


def model_args(config: configparser.ConfigParser) -> list[str]:
    provider = config.get("model", "provider", fallback="local").strip().lower()
    args = ["--provider", provider]
    model = config.get("model", "model", fallback="").strip()
    if model:
        args += ["--model", model]
    if provider == "local":
        args += ["--base-url", config.get("model", "base_url").strip()]
    return args


def setup(config: configparser.ConfigParser) -> None:
    try:
        import numpy, sklearn  # noqa: F401  quick check that dependencies are installed
    except ImportError:
        sys.exit("Dependencies aren't installed. Run: uv sync")
    build_index(config)
    print("\nSetup complete. Next: uv run run.py check")


def build_index(config: configparser.ConfigParser) -> None:
    from rag.cli import main as rag_main

    docs = str(ROOT / config.get("knowledge_base", "docs", fallback="data/kb"))
    backend = config.get("knowledge_base", "embedding", fallback="fastembed").strip()
    print(f"\nBuilding the knowledge base index with '{backend}'...")
    try:
        rag_main(["ingest", "--docs", docs, "--index", str(INDEX_DIR), "--backend", backend])
    except Exception as exc:
        if backend != "fastembed":
            raise
        print(f"Couldn't load the embedding model ({exc}).\nFalling back to keyword search (tfidf).")
        rag_main(["ingest", "--docs", docs, "--index", str(INDEX_DIR), "--backend", "tfidf"])


def ensure_index(config: configparser.ConfigParser) -> None:
    if not (INDEX_DIR / "index.json").exists():
        build_index(config)


def check(config: configparser.ConfigParser) -> None:
    provider = config.get("model", "provider", fallback="local").strip().lower()
    model = config.get("model", "model", fallback="").strip()

    if provider == "claude":
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is set. You're ready: uv run run.py ask \"jsmith can't sign in\"")
        else:
            print("provider = claude, but ANTHROPIC_API_KEY isn't set. Set it, or change provider to local in config.ini.")
        return

    base_url = config.get("model", "base_url").strip().rstrip("/")
    print(f"Checking for a local model server at {base_url} ...")
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=5) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError):
        print("No server answered.")
        print("  Ollama:    open the Ollama app, or run: ollama serve")
        print("  LM Studio: open the Developer tab and start the server")
        print("Then make sure base_url in config.ini matches it.")
        sys.exit(1)

    names = [m.get("id", "") for m in data.get("data", [])]
    if not names:
        print("The server is running but has no models. Ollama: ollama pull qwen2.5:7b")
        sys.exit(1)
    print("Server is running. Models available:")
    for name in names:
        print(f"  - {name}")
    if model and model not in names:
        print(f"\nThe model in config.ini ('{model}') isn't in that list.")
        print("Copy one of the names above into the model line of config.ini.")
        sys.exit(1)
    print(f"\nUsing '{model or names[0]}'. You're ready: uv run run.py ask \"jsmith can't sign in\"")


def ask(config: configparser.ConfigParser, question: str | None) -> None:
    from agent.cli import main as agent_main

    ensure_index(config)
    command = ["ask", question] if question else ["chat"]
    command += ["--index", str(INDEX_DIR), "--max-steps", config.get("agent", "max_steps", fallback="8")]
    if config.getboolean("agent", "trace", fallback=True):
        command.append("--trace")
    agent_main(command + model_args(config))


def rag(config: configparser.ConfigParser, question: str) -> None:
    from rag.cli import main as rag_main

    ensure_index(config)
    rag_main(["ask", question, "--index", str(INDEX_DIR), "--sources"] + model_args(config))


def main() -> None:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        print(__doc__)
        return

    command, rest = sys.argv[1], sys.argv[2:]
    if command == "setup":
        setup(load_config())
        return

    config = load_config()
    if command == "check":
        check(config)
    elif command == "ask":
        if not rest:
            sys.exit('Add a question in quotes, for example: uv run run.py ask "jsmith can\'t sign in"')
        ask(config, " ".join(rest))
    elif command == "chat":
        ask(config, None)
    elif command == "rag":
        if not rest:
            sys.exit('Add a question in quotes, for example: uv run run.py rag "how do I clear stuck print jobs"')
        rag(config, " ".join(rest))
    else:
        sys.exit(f"Unknown command '{command}'. Run: uv run run.py help")


if __name__ == "__main__":
    main()
