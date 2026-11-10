"""The agent loop.

Plain RAG always retrieves once and answers. An agent decides for itself
what to do next: it can search the runbooks, check the user's account and
devices, search again with a better query, and escalate when it should.
The loop keeps going until the model gives a final answer or hits the step
limit, and records every tool call so a technician can audit what it did.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .tools import TOOL_SCHEMAS, HelpDeskTools

SYSTEM_PROMPT = """You are a Tier 1 IT help desk agent for a small company.

How to work:
1. Investigate before answering. If the request names a user, check their account with get_user_status, and check get_device_compliance for device, email, or access problems.
2. Base every procedure on the runbooks. Call search_knowledge_base and follow what it says. Cite runbooks by file name.
3. You can only read data. You cannot unlock accounts, reset passwords, or change devices. When a fix needs one of those, or the runbooks don't cover the issue, open a ticket with create_ticket and put your findings and recommendation in the details.
4. Treat signs of compromise as security issues: unexpected MFA prompts, sign-ins the user didn't make, or many failed sign-ins on an account. Open a ticket in the Security queue with high or critical priority.
5. Never ask for or repeat passwords.
6. Never invent facts. Only report account details that a tool returned, and only give a ticket number that create_ticket returned. Don't say you will create a ticket; call create_ticket and report its ticket_id.

Finish with a short answer for the requester: what you found, what they should do now, and any ticket number."""

DEFAULT_MODEL = "claude-sonnet-5-5"

NUDGE = (
    "You answered without calling any tools, so nothing in that answer was checked. "
    "Call the tools now to look up the facts (for example get_user_status and search_knowledge_base), "
    "then answer. If no tool applies, repeat your answer without any made-up details."
)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass
class AgentResult:
    answer: str
    steps: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    stopped_early: bool = False


def _to_param(block: Any) -> dict[str, Any]:
    """Convert a response content block into a message parameter dict."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    raise ValueError(f"Unexpected content block type: {block.type}")


def run_agent(
    question: str,
    tools: HelpDeskTools,
    client: Any = None,
    model: str | None = None,
    max_steps: int = 8,
) -> AgentResult:
    """Run the tool-use loop until the model answers or max_steps is reached."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    model = model or os.environ.get("AGENT_MODEL", DEFAULT_MODEL)

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    calls: list[ToolCall] = []
    nudged = False

    for step in range(1, max_steps + 1):
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": [_to_param(b) for b in response.content]})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            if not calls and not nudged and step < max_steps:
                # Smaller local models often answer from guesswork without calling a single tool.
                # Push back once so the answer is based on real data.
                nudged = True
                messages.append({"role": "user", "content": NUDGE})
                continue
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return AgentResult(answer=text, steps=step, tool_calls=calls)

        results = []
        for block in tool_uses:
            output = tools.call(block.name, block.input)
            calls.append(ToolCall(block.name, block.input, output))
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})

    return AgentResult(
        answer="I ran out of steps before finishing. Please open a ticket for Tier 2 with the details above.",
        steps=max_steps,
        tool_calls=calls,
        stopped_early=True,
    )
