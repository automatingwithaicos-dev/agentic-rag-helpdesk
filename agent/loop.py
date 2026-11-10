"""The agent loop.

Plain RAG always retrieves once and answers. An agent decides for itself
what to do next: it can search the runbooks, check the user's account and
devices, search again with a better query, and escalate when it should.
The loop keeps going until the model gives a final answer or hits the step
limit, and records every tool call so a technician can audit what it did.
"""

from __future__ import annotations

import json
import os
import re
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
6. Point out security gaps you see in tool results even if the user didn't ask, such as an account with no MFA methods registered.
7. A disabled account usually means the user was offboarded. Never recommend re-enabling it without confirmation from the user's manager or HR.
8. Never invent facts. Only report account details that a tool returned, and only give a ticket number that create_ticket returned. Don't say you will create a ticket; call create_ticket and report its ticket_id.

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


UNVERIFIED = (
    "The model answered without using any tools, so its answer couldn't be checked and was not shown. "
    "This usually means the model doesn't support tool calling. Pick a model with tool support "
    "(in LM Studio, look for the tool-use badge; for example Qwen2.5 7B Instruct or Llama 3.1 8B Instruct), "
    "put its name in config.ini, and try again."
)


@dataclass
class AgentResult:
    answer: str
    steps: int
    tool_calls: list[ToolCall] = field(default_factory=list)
    stopped_early: bool = False
    unverified_answer: str | None = None  # what the model said when it refused to use tools
    review_notes: list[str] = field(default_factory=list)  # policy problems the model never fixed


def _to_param(block: Any) -> dict[str, Any]:
    """Convert a response content block into a message parameter dict."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    raise ValueError(f"Unexpected content block type: {block.type}")


FAILED_SIGN_IN_THRESHOLD = 10
_TICKET_CLAIM = re.compile(r"(ticket[^\n]{0,25}?|#)\s*([A-Z]{1,4}-?)?\d{3,}", re.IGNORECASE)


def _tickets_created(calls: list[ToolCall]) -> list[dict[str, Any]]:
    return [{**c.arguments, **json.loads(c.result)} for c in calls if c.name == "create_ticket"]


def _invented_ticket_numbers(text: str, calls: list[ToolCall]) -> list[str]:
    """Ticket numbers in the answer that create_ticket never returned."""
    real = {t.get("ticket_id") for t in _tickets_created(calls)}
    claims = [m.group(0) for m in _TICKET_CLAIM.finditer(text)]
    return [c for c in claims if not any(r and r in c for r in real)]


def review_answer(text: str, calls: list[ToolCall]) -> list[str]:
    """Policy checks run in code, because small models don't always follow the prompt.

    Returns a list of problems to send back to the model. Empty means the answer passes.
    """
    problems = []
    if _invented_ticket_numbers(text, calls):
        problems.append(
            "Your answer mentions a ticket number, but you never called create_ticket, so that number is made up. "
            "If a ticket is needed, call create_ticket and report the ticket_id it returns. Otherwise remove the ticket number."
        )
    security_tickets = [t for t in _tickets_created(calls) if t.get("queue") == "Security"]
    lowered = text.lower()
    for c in calls:
        if c.name != "get_user_status":
            continue
        status = json.loads(c.result)
        name = status.get("username")
        if status.get("mfa_methods") == [] and status.get("enabled", True) and "mfa" not in lowered \
                and "multi-factor" not in lowered:
            problems.append(
                f"get_user_status shows {name} has no MFA methods registered. That's a security gap. "
                "Tell the user and include the MFA setup steps from the runbook (search_knowledge_base 'MFA setup')."
            )
        if status.get("enabled") is False and not any(w in lowered for w in ("manager", "hr ", "hr.", "hr,", "human resources")):
            problems.append(
                f"{name}'s account is disabled, which usually means they were offboarded. Say that re-enabling "
                "requires confirmation from their manager or HR (see onboarding-offboarding.md), and don't "
                "recommend turning it back on without that approval."
            )
        failed = status.get("failed_sign_ins_last_hour", 0) or 0
        if failed >= FAILED_SIGN_IN_THRESHOLD and not security_tickets:
            problems.append(
                f"get_user_status shows {failed} failed sign-ins in the last hour for {status.get('username')}. "
                f"Policy treats {FAILED_SIGN_IN_THRESHOLD} or more as a possible password attack. Call create_ticket "
                "with queue Security and priority high before answering, and do not recommend unlocking the account "
                "until Security has reviewed it."
            )
    return problems


def _remove_invented_tickets(text: str, calls: list[ToolCall]) -> str:
    for claim in _invented_ticket_numbers(text, calls):
        text = text.replace(claim, "(no ticket was created)")
    return text


def _looks_like_a_claim(text: str) -> bool:
    """True if a tool-less answer states facts it could only know from a tool."""
    lowered = text.lower()
    markers = ("ticket", "locked", "account", "device", "compliant", "mfa", "status", "```")
    return any(m in lowered for m in markers)


def run_agent(
    question: str,
    tools: HelpDeskTools,
    client: Any = None,
    model: str | None = None,
    max_steps: int = 8,
    max_tool_calls: int = 12,
) -> AgentResult:
    """Run the tool-use loop until the model answers or max_steps is reached."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    model = model or os.environ.get("AGENT_MODEL", DEFAULT_MODEL)

    if hasattr(tools, "start_request"):
        tools.start_request()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    calls: list[ToolCall] = []
    nudged = False
    reviews_left = 2

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
            if not calls and nudged and _looks_like_a_claim(text):
                return AgentResult(answer=UNVERIFIED, steps=step, unverified_answer=text)
            problems = review_answer(text, calls)
            if problems and reviews_left > 0 and step < max_steps:
                reviews_left -= 1
                review = "Before this answer goes to the user, fix these problems:\n- " + "\n- ".join(problems)
                messages.append({"role": "user", "content": review})
                continue
            return AgentResult(answer=_remove_invented_tickets(text, calls), steps=step, tool_calls=calls,
                               review_notes=problems)

        if len(calls) + len(tool_uses) > max_tool_calls:
            break
        results = []
        for block in tool_uses:
            output = tools.call(block.name, block.input)
            calls.append(ToolCall(block.name, block.input, output))
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})

    opened = [t["ticket_id"] for t in _tickets_created(calls) if t.get("created")]
    note = f" Tickets opened: {', '.join(opened)}." if opened else ""
    return AgentResult(
        answer="I ran out of steps before finishing." + note + " Please have a technician review this request.",
        steps=step,
        tool_calls=calls,
        stopped_early=True,
    )
