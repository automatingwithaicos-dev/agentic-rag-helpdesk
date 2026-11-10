"""Tools the agent can call.

Every tool here is read-only except create_ticket, which only records an
escalation. The agent can investigate and recommend, but any change to an
account (unlocking, resetting, wiping) is left to a human technician. In a
real deployment these functions would call Microsoft Graph, Intune, and a PSA
like ConnectWise; here they read sample data so the project runs anywhere.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from rag.store import VectorIndex

DEFAULT_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "mock" / "directory.json"

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the IT help desk runbooks for procedures and troubleshooting steps. "
            "Use this before giving any instructions so answers follow company procedure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for, in plain words."},
                "k": {"type": "integer", "description": "How many passages to return (1 to 5).", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_user_status",
        "description": (
            "Look up a user's account status: enabled, locked out, failed sign-ins in the last hour, "
            "password age, registered MFA methods, groups, and license."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"username": {"type": "string", "description": "The user's username, like jsmith."}},
            "required": ["username"],
        },
    },
    {
        "name": "get_device_compliance",
        "description": "List a user's Intune-managed devices with compliance state, failing policies, and last check-in.",
        "input_schema": {
            "type": "object",
            "properties": {"username": {"type": "string"}},
            "required": ["username"],
        },
    },
    {
        "name": "create_ticket",
        "description": (
            "Escalate to a human technician by opening a ticket. Use this when the fix needs an account "
            "change, the runbooks don't cover the issue, or there are signs of a security problem."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line summary of the issue."},
                "details": {"type": "string", "description": "What you checked, what you found, and what you recommend."},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "queue": {"type": "string", "enum": ["Tier 2", "Security"]},
            },
            "required": ["summary", "details", "priority", "queue"],
        },
    },
]


class HelpDeskTools:
    """Implements the tools above against a vector index and a directory file."""

    def __init__(self, index: VectorIndex, directory_path: str | Path = DEFAULT_DIRECTORY):
        self.index = index
        self.directory = json.loads(Path(directory_path).read_text(encoding="utf-8"))
        self.tickets: list[dict[str, Any]] = []
        self._seen_calls: dict[str, str] = {}
        self._open_by_queue: dict[str, str] = {}
        self._handlers: dict[str, Callable[..., Any]] = {
            "search_knowledge_base": self.search_knowledge_base,
            "get_user_status": self.get_user_status,
            "get_device_compliance": self.get_device_compliance,
            "create_ticket": self.create_ticket,
        }

    def start_request(self) -> None:
        """Reset per-request state. Called by the agent at the start of each new request."""
        self._seen_calls = {}
        self._open_by_queue = {}

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Run a tool by name and return its result as a JSON string for the model.

        Repeating the exact same call in one request returns the earlier result instead
        of running it again, so a model stuck in a loop can't open duplicate tickets.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        key = f"{name}:{json.dumps(arguments, sort_keys=True)}"
        if key in self._seen_calls:
            earlier = json.loads(self._seen_calls[key])
            earlier["note"] = "You already made this exact call. This is the earlier result. Don't repeat it; answer the user."
            return json.dumps(earlier)
        try:
            result = json.dumps(handler(**arguments))
        except TypeError as exc:
            return json.dumps({"error": f"Bad arguments for {name}: {exc}"})
        self._seen_calls[key] = result
        return result

    def search_knowledge_base(self, query: str, k: int = 3) -> dict[str, Any]:
        k = max(1, min(int(k), 5))
        results = self.index.search(query, k=k)
        return {
            "passages": [
                {"source": c.source, "title": c.title, "score": round(score, 3), "text": c.text}
                for c, score in results
            ]
        }

    def get_user_status(self, username: str) -> dict[str, Any]:
        user = self.directory["users"].get(username.lower())
        if user is None:
            return {"error": f"No user named '{username}'. Ask the requester to confirm the username."}
        return {"username": username.lower(), **user}

    def get_device_compliance(self, username: str) -> dict[str, Any]:
        username = username.lower()
        if username not in self.directory["users"]:
            return {"error": f"No user named '{username}'."}
        return {"username": username, "devices": self.directory["devices"].get(username, [])}

    def create_ticket(self, summary: str, details: str, priority: str, queue: str) -> dict[str, Any]:
        existing = self._open_by_queue.get(queue)
        if existing:
            return {
                "created": False,
                "ticket_id": existing,
                "queue": queue,
                "note": f"{existing} is already open in the {queue} queue for this request. Don't create another; report {existing}.",
            }
        ticket = {
            "id": f"TCK-{1001 + len(self.tickets)}",
            "summary": summary,
            "details": details,
            "priority": priority,
            "queue": queue,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.tickets.append(ticket)
        self._open_by_queue[queue] = ticket["id"]
        return {"created": True, "ticket_id": ticket["id"], "queue": queue}
