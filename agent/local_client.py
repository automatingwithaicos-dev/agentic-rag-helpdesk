"""Run the agent on a local model instead of the Claude API.

Ollama, LM Studio, llama.cpp's server, and vLLM all expose an
OpenAI-compatible chat API. This adapter translates between that format
and the Anthropic-style messages the agent loop uses, so the loop itself
doesn't change. Nothing leaves your machine and no API key is needed.

Defaults point at Ollama (http://localhost:11434/v1). For LM Studio use
--base-url http://localhost:1234/v1. Pick a model that supports tool
calling, such as qwen2.5, llama3.1, or mistral-nemo.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"


def to_openai_tools(tool_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_schemas
    ]


def to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
            continue
        if msg["role"] == "assistant":
            text = "".join(b["text"] for b in content if b["type"] == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                }
                for b in content
                if b["type"] == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        else:
            for b in content:
                if b["type"] == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
                elif b["type"] == "text":
                    out.append({"role": "user", "content": b["text"]})
    return out


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def from_openai_response(response: Any) -> SimpleNamespace:
    """Convert an OpenAI-style chat completion into Anthropic-style content blocks."""
    message = response.choices[0].message
    blocks: list[SimpleNamespace] = []
    if message.content:
        blocks.append(SimpleNamespace(type="text", text=message.content))
    for i, call in enumerate(message.tool_calls or []):
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                id=call.id or f"call_{i}",
                name=call.function.name,
                input=_parse_arguments(call.function.arguments),
            )
        )
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=blocks, stop_reason=stop)


class LocalModelClient:
    """Looks like anthropic.Anthropic() to the agent loop, but calls a local model."""

    def __init__(self, base_url: str | None = None, openai_client: Any = None):
        if openai_client is None:
            from openai import OpenAI

            openai_client = OpenAI(
                base_url=base_url or os.environ.get("LOCAL_BASE_URL", DEFAULT_BASE_URL),
                api_key="local",  # local servers ignore the key, but the client requires one
            )
        self._openai = openai_client
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, model: str, max_tokens: int, system: str, tools: list, messages: list) -> SimpleNamespace:
        response = self._openai.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=to_openai_messages(system, messages),
            tools=to_openai_tools(tools),
        )
        return from_openai_response(response)
