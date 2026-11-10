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


def test_agent_pushes_back_once_when_model_skips_tools(tools):
    client = FakeClient([
        response([text("jsmith is locked out. Ticket T00123456789.")], "end_turn"),
        response([tool_use("t1", "get_user_status", {"username": "mgarcia"})], "tool_use"),
        response([text("mgarcia's account is enabled and not locked.")], "end_turn"),
    ])
    result = run_agent("mgarcia can't sign in", tools, client=client, model="fake")
    assert [c.name for c in result.tool_calls] == ["get_user_status"]
    assert "T00123456789" not in result.answer
    sent = client.requests[-1]["messages"]
    assert any(m["role"] == "user" and isinstance(m["content"], str) and "without calling any tools" in m["content"] for m in sent)


def test_agent_can_still_answer_without_tools_after_one_push(tools):
    client = FakeClient([
        response([text("Hello! What can I help with?")], "end_turn"),
        response([text("Hello! What can I help with?")], "end_turn"),
    ])
    result = run_agent("hi", tools, client=client, model="fake")
    assert result.answer == "Hello! What can I help with?" and result.tool_calls == []


def test_agent_stops_at_step_limit(tools):
    looping = [response([tool_use(f"t{i}", "search_knowledge_base", {"query": "vpn"})], "tool_use") for i in range(3)]
    result = run_agent("vpn broken", tools, client=FakeClient(looping), model="fake", max_steps=3)
    assert result.stopped_early and len(result.tool_calls) == 3


def test_unverified_claims_are_replaced_with_guidance(tools):
    fake_answer = "jsmith's account is locked. Ticket ID: 1234567890"
    client = FakeClient([response([text(fake_answer)], "end_turn"), response([text(fake_answer)], "end_turn")])
    result = run_agent("jsmith can't sign in", tools, client=client, model="fake")
    assert "1234567890" not in result.answer
    assert "tool calling" in result.answer
    assert result.unverified_answer == fake_answer


def test_review_catches_invented_ticket_and_missing_security_escalation(tools):
    client = FakeClient([
        response([tool_use("t1", "get_user_status", {"username": "jsmith"})], "tool_use"),
        response([text("Unlock the account. -ticket created: #456789")], "end_turn"),
        response([tool_use("t2", "create_ticket", {
            "summary": "jsmith: 12 failed sign-ins", "details": "Possible password attack.",
            "priority": "high", "queue": "Security"})], "tool_use"),
        response([text("Possible password attack on your account. Security ticket TCK-1001 is open.")], "end_turn"),
    ])
    result = run_agent("jsmith can't sign in", tools, client=client, model="fake")

    reviews = [m["content"] for m in client.requests[-1]["messages"]
               if m["role"] == "user" and isinstance(m["content"], str) and m["content"].startswith("Before this answer")]
    assert len(reviews) == 1 and "made up" in reviews[0] and "queue Security" in reviews[0]
    assert tools.tickets[0]["queue"] == "Security"
    assert "TCK-1001" in result.answer and result.review_notes == []


def test_invented_ticket_is_removed_if_model_never_fixes_it(tools):
    stubborn = response([text("All set. Ticket #456789.")], "end_turn")
    client = FakeClient([
        response([tool_use("t1", "get_device_compliance", {"username": "mgarcia"})], "tool_use"),
        stubborn, stubborn, stubborn,
    ])
    result = run_agent("mgarcia email broken", tools, client=client, model="fake")
    assert "456789" not in result.answer
    assert "(no ticket was created)" in result.answer
    assert result.review_notes


def test_real_ticket_numbers_pass_review(tools):
    tools.call("create_ticket", {"summary": "a", "details": "b", "priority": "low", "queue": "Tier 2"})
    from agent.loop import ToolCall, review_answer
    calls = [ToolCall("create_ticket", {"queue": "Tier 2"}, json.dumps({"created": True, "ticket_id": "TCK-1001", "queue": "Tier 2"}))]
    assert review_answer("I opened ticket TCK-1001 for you.", calls) == []


def test_duplicate_tickets_are_blocked(tools):
    args = {"summary": "jsmith attack", "details": "12 failed", "priority": "high", "queue": "Security"}
    first = json.loads(tools.call("create_ticket", args))
    again = json.loads(tools.call("create_ticket", args))
    reworded = json.loads(tools.call("create_ticket", {**args, "summary": "jsmith possible attack"}))
    assert first["ticket_id"] == again["ticket_id"] == reworded["ticket_id"] == "TCK-1001"
    assert reworded["created"] is False and len(tools.tickets) == 1


def test_new_request_can_open_a_new_ticket(tools):
    args = {"summary": "a", "details": "b", "priority": "low", "queue": "Tier 2"}
    tools.call("create_ticket", args)
    tools.start_request()
    assert json.loads(tools.call("create_ticket", args))["ticket_id"] == "TCK-1002"


def test_looping_model_opens_one_ticket_and_stops(tools):
    ticket = {"summary": "x", "details": "y", "priority": "high", "queue": "Security"}
    loop = [response([tool_use(f"a{i}", "create_ticket", ticket), tool_use(f"b{i}", "create_ticket", ticket)], "tool_use")
            for i in range(10)]
    result = run_agent("jsmith can't sign in", tools, client=FakeClient(loop), model="fake", max_steps=10, max_tool_calls=6)
    assert len(tools.tickets) == 1
    assert result.stopped_early and len(result.tool_calls) <= 6
    assert "TCK-1001" in result.answer
