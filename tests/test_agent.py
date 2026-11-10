"""Agent tests use a scripted fake model, so they run offline with no API key."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.loop import run_agent
from agent.tools import TOOL_SCHEMAS, HelpDeskTools
from rag.loader import load_documents
from rag.store import VectorIndex

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, args):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=args)


def response(blocks, stop_reason):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class FakeClient:
    """Returns pre-scripted responses and records what the agent sent."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self._scripted.pop(0)


@pytest.fixture(scope="module")
def index():
    return VectorIndex.build(load_documents(KB), backend="tfidf")


@pytest.fixture
def tools(index):
    return HelpDeskTools(index)


def test_tool_schemas_match_handlers(tools):
    for schema in TOOL_SCHEMAS:
        assert schema["name"] in tools._handlers


def test_user_lookup_and_unknown_user(tools):
    status = json.loads(tools.call("get_user_status", {"username": "JSmith"}))
    assert status["locked_out"] is True
    missing = json.loads(tools.call("get_user_status", {"username": "nobody"}))
    assert "error" in missing


def test_device_compliance_shows_failing_policy(tools):
    devices = json.loads(tools.call("get_device_compliance", {"username": "mgarcia"}))["devices"]
    assert devices[0]["failing_policies"] == ["BitLocker not enabled"]


def test_bad_tool_name_and_arguments_return_errors(tools):
    assert "error" in json.loads(tools.call("delete_everything", {}))
    assert "error" in json.loads(tools.call("get_user_status", {"user": "jsmith"}))


def test_create_ticket_numbers_tickets(tools):
    first = json.loads(tools.call("create_ticket", {"summary": "a", "details": "b", "priority": "low", "queue": "Tier 2"}))
    second = json.loads(tools.call("create_ticket", {"summary": "c", "details": "d", "priority": "high", "queue": "Security"}))
    assert (first["ticket_id"], second["ticket_id"]) == ("TCK-1001", "TCK-1002")


def test_agent_investigates_then_escalates(tools):
    client = FakeClient([
        response([tool_use("t1", "get_user_status", {"username": "jsmith"})], "tool_use"),
        response([tool_use("t2", "search_knowledge_base", {"query": "account lockout unlock"})], "tool_use"),
        response([tool_use("t3", "create_ticket", {
            "summary": "jsmith locked out after 12 failed sign-ins",
            "details": "Account locked. Possible stale password on phone, or password spraying.",
            "priority": "high",
            "queue": "Security",
        })], "tool_use"),
        response([text("Your account is locked. I opened TCK-1001 with Security.")], "end_turn"),
    ])

    result = run_agent("jsmith can't sign in", tools, client=client, model="fake")

    assert [c.name for c in result.tool_calls] == ["get_user_status", "search_knowledge_base", "create_ticket"]
    assert "TCK-1001" in result.answer
    assert tools.tickets[0]["queue"] == "Security"
    assert result.steps == 4 and not result.stopped_early

    # Each tool result goes back to the model, matched to its tool_use id.
    last_request = client.requests[-1]["messages"]
    tool_results = [m for m in last_request if m["role"] == "user" and isinstance(m["content"], list)]
    assert [r["content"][0]["tool_use_id"] for r in tool_results] == ["t1", "t2", "t3"]
    assert "password-reset.md" in tool_results[1]["content"][0]["content"]


def test_agent_answers_directly_without_tools(tools):
    client = FakeClient([response([text("Hello! What can I help with?")], "end_turn")])
    result = run_agent("hi", tools, client=client, model="fake")
    assert result.answer == "Hello! What can I help with?" and result.tool_calls == []


def test_agent_stops_at_step_limit(tools):
    looping = [response([tool_use(f"t{i}", "search_knowledge_base", {"query": "vpn"})], "tool_use") for i in range(3)]
    result = run_agent("vpn broken", tools, client=FakeClient(looping), model="fake", max_steps=3)
    assert result.stopped_early and len(result.tool_calls) == 3
