import json

import httpx
import pytest

from hcq.agent.llm import LLMError, OllamaChat, ScriptedLLM
from hcq.agent.schemas import Incident, TicketDraft
from hcq.agent.tools import ToolBox
from hcq.todo import is_todo, todo


def test_todo_marker():
    @todo("Milestone X")
    def later():
        return 1

    assert is_todo(later)
    with pytest.raises(NotImplementedError, match="Milestone X"):
        later()


def test_toolbox_hides_unimplemented_tools():
    box = ToolBox(con=None)  # type: ignore[arg-type]
    names = {spec["function"]["name"] for spec in box.specs()}
    assert {"get_listing", "get_master_hotel", "sample_issues"} <= names
    for spec in box.specs():
        assert spec["type"] == "function"
        assert spec["function"]["parameters"]["type"] == "object"


def test_toolbox_returns_errors_as_json():
    box = ToolBox(con=None)  # type: ignore[arg-type]
    assert "unknown tool" in json.loads(box.call("drop_table", {}))["error"]
    assert "not valid JSON" in json.loads(box.call("get_master_hotel", "{oops"))["error"]


def _ollama(handler) -> OllamaChat:
    return OllamaChat("http://ollama.test", "qwen3:14b", transport=httpx.MockTransport(handler))


def test_ollama_chat_sends_tools_and_schema_and_returns_message():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "x", "arguments": {}}}],
                }
            },
        )

    msg = _ollama(handler).chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function"}],
        schema=TicketDraft.model_json_schema(),
    )
    assert msg["tool_calls"][0]["function"]["name"] == "x"
    assert seen["stream"] is False and seen["tools"] and seen["format"]["type"] == "object"
    assert "think" not in seen  # only sent when configured


def test_ollama_missing_model_explains_fix():
    llm = _ollama(lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError, match="ollama pull qwen3:14b"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_scripted_llm_records_calls():
    llm = ScriptedLLM([{"role": "assistant", "content": "ok"}])
    assert llm.chat([{"role": "user", "content": "x"}])["content"] == "ok"
    assert len(llm.calls) == 1
    with pytest.raises(LLMError):
        llm.chat([])


def test_incident_model_roundtrip():
    incident = Incident(
        incident_id="a",
        partner="rheinland",
        check_code="GEO_SWAPPED",
        first_seen="2026-10-08",
        last_seen="2026-10-10",
        issue_count=3,
        affected_listings=3,
        daily_counts={"2026-10-08": 3},
    )
    assert Incident.model_validate_json(incident.model_dump_json()) == incident
