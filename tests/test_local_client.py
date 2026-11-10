"""Tests for the local-model adapter, using a fake OpenAI-compatible server."""

import json
from pathlib import Path
from types import SimpleNamespace

from agent.local_client import LocalModelClient, from_openai_response, to_openai_messages, to_openai_tools
from agent.loop import run_agent
from agent.tools import TOOL_SCHEMAS, HelpDeskTools
from rag.loader import load_documents
from rag.store import VectorIndex

KB = Path(__file__).resolve().parent.parent / "data" / "kb"


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def call(id_, name, args):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeOpenAI:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self._scripted.pop(0)


def test_tools_convert_to_openai_functions():
    converted = to_openai_tools(TOOL_SCHEMAS)
    assert converted[0]["type"] == "function"
    assert converted[0]["function"]["parameters"] == TOOL_SCHEMAS[0]["input_schema"]


def test_messages_convert_tool_calls_and_results():
    messages = [
        {"role": "user", "content": "jsmith locked out"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "c1", "name": "get_user_status", "input": {"username": "jsmith"}},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{}"}]},
    ]
    out = to_openai_messages("sys", messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"username": "jsmith"}'
    assert out[3]["tool_call_id"] == "c1"


def test_response_with_bad_json_arguments_does_not_crash():
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_user_status", arguments="{not json"))
    result = from_openai_response(completion(tool_calls=[bad]))
    assert result.stop_reason == "tool_use" and result.content[0].input == {}


def test_agent_runs_end_to_end_on_local_adapter():
    tools = HelpDeskTools(VectorIndex.build(load_documents(KB), backend="tfidf"))
    fake = FakeOpenAI([
        completion(tool_calls=[call("c1", "get_device_compliance", {"username": "mgarcia"})]),
        completion(tool_calls=[call("c2", "search_knowledge_base", {"query": "BitLocker not compliant"})]),
        completion(content="Your laptop is blocked because BitLocker is off. Restart it so encryption can start."),
    ])
    result = run_agent("mgarcia can't get email", tools, client=LocalModelClient(openai_client=fake), model="qwen2.5:7b")

    assert [c.name for c in result.tool_calls] == ["get_device_compliance", "search_knowledge_base"]
    assert "BitLocker" in result.answer
    final_request = fake.requests[-1]["messages"]
    assert final_request[0]["role"] == "system"
    assert sum(1 for m in final_request if m["role"] == "tool") == 2
