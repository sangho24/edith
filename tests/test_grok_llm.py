"""PR #13 — GrokLLM 변환 + 호출 테스트.

xAI API 직접 호출 없이 mock client 로 검증.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.llm import (
    GrokLLM,
    LLMResponse,
    _anthropic_messages_to_openai,
    _anthropic_tools_to_openai,
    _openai_response_to_anthropic,
    get_llm,
)

# ── Tool 변환 ────────────────────────────────────────────────────────────


def test_tools_translation_basic() -> None:
    anthropic_tools = [
        {
            "name": "wiki_read",
            "description": "Read wiki page",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]
    out = _anthropic_tools_to_openai(anthropic_tools)
    assert out is not None
    assert len(out) == 1
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "wiki_read"
    assert out[0]["function"]["description"] == "Read wiki page"
    assert out[0]["function"]["parameters"]["properties"]["path"]["type"] == "string"


def test_tools_translation_empty() -> None:
    assert _anthropic_tools_to_openai([]) is None


def test_tools_translation_no_input_schema() -> None:
    """input_schema 누락된 tool 도 graceful."""
    anthropic_tools = [{"name": "noop", "description": "no-op"}]
    out = _anthropic_tools_to_openai(anthropic_tools)
    assert out is not None
    assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ── Message 변환 ─────────────────────────────────────────────────────────


def test_messages_simple_user_string() -> None:
    msgs = [{"role": "user", "content": "안녕"}]
    out = _anthropic_messages_to_openai(msgs, system="당신은 Edith")
    assert out[0] == {"role": "system", "content": "당신은 Edith"}
    assert out[1] == {"role": "user", "content": "안녕"}


def test_messages_tool_result_translates_to_tool_role() -> None:
    """user content 가 tool_result blocks list 면 'tool' role 메시지로 split."""
    msgs = [
        {"role": "user", "content": "wiki 확인해줘"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "wiki_read",
                    "input": {"path": "entities/김교수.md"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "내용"},
            ],
        },
    ]
    out = _anthropic_messages_to_openai(msgs, system="")

    # system 빈 문자열이면 빠짐
    assert out[0]["role"] == "user"
    assert out[1]["role"] == "assistant"
    assert "tool_calls" in out[1]
    assert out[1]["tool_calls"][0]["id"] == "tu_1"
    assert out[1]["tool_calls"][0]["function"]["name"] == "wiki_read"
    assert json.loads(out[1]["tool_calls"][0]["function"]["arguments"]) == {
        "path": "entities/김교수.md"
    }
    assert out[2] == {"role": "tool", "tool_call_id": "tu_1", "content": "내용"}


def test_messages_assistant_text_only() -> None:
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "text", "text": "안녕하세요"}]},
    ]
    out = _anthropic_messages_to_openai(msgs, system="sys")
    assert out[2]["role"] == "assistant"
    assert out[2]["content"] == "안녕하세요"
    assert "tool_calls" not in out[2]


def test_messages_assistant_text_and_tool_use() -> None:
    """text + tool_use 가 같이 있는 경우 — content + tool_calls 둘 다 채움."""
    msgs = [
        {"role": "user", "content": "확인해줘"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "확인합니다"},
                {
                    "type": "tool_use",
                    "id": "tu_2",
                    "name": "emit_log",
                    "input": {"msg": "test"},
                },
            ],
        },
    ]
    out = _anthropic_messages_to_openai(msgs, system="")
    asst = out[1]
    assert asst["role"] == "assistant"
    assert asst["content"] == "확인합니다"
    assert asst["tool_calls"][0]["function"]["name"] == "emit_log"


# ── Response 변환 ────────────────────────────────────────────────────────


def _make_openai_resp(
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    usage_in: int = 10,
    usage_out: int = 5,
) -> Any:
    """Mock OpenAI ChatCompletion 응답 객체 생성."""
    msg = MagicMock()
    msg.content = content
    if tool_calls:
        tc_list = []
        for tc in tool_calls:
            tc_obj = MagicMock()
            tc_obj.id = tc["id"]
            tc_obj.function = MagicMock()
            tc_obj.function.name = tc["name"]
            tc_obj.function.arguments = json.dumps(tc.get("args", {}))
            tc_list.append(tc_obj)
        msg.tool_calls = tc_list
    else:
        msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = usage_in
    usage.completion_tokens = usage_out

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def test_response_text_only_end_turn() -> None:
    resp = _make_openai_resp(content="안녕하세요", finish_reason="stop")
    out = _openai_response_to_anthropic(resp)
    assert out.stop_reason == "end_turn"
    assert out.text == "안녕하세요"
    assert len(out.content_blocks) == 1
    assert out.content_blocks[0] == {"type": "text", "text": "안녕하세요"}
    assert out.usage_in == 10
    assert out.usage_out == 5


def test_response_tool_use() -> None:
    resp = _make_openai_resp(
        content=None,
        tool_calls=[{"id": "call_1", "name": "wiki_read", "args": {"path": "x.md"}}],
        finish_reason="tool_calls",
    )
    out = _openai_response_to_anthropic(resp)
    assert out.stop_reason == "tool_use"
    assert len(out.content_blocks) == 1
    block = out.content_blocks[0]
    assert block["type"] == "tool_use"
    assert block["id"] == "call_1"
    assert block["name"] == "wiki_read"
    assert block["input"] == {"path": "x.md"}


def test_response_text_with_tool_use() -> None:
    resp = _make_openai_resp(
        content="확인합니다",
        tool_calls=[{"id": "c1", "name": "emit_log", "args": {"msg": "test"}}],
        finish_reason="tool_calls",
    )
    out = _openai_response_to_anthropic(resp)
    assert out.stop_reason == "tool_use"
    assert len(out.content_blocks) == 2
    assert out.content_blocks[0]["type"] == "text"
    assert out.content_blocks[1]["type"] == "tool_use"


def test_response_max_tokens() -> None:
    resp = _make_openai_resp(content="잘리...", finish_reason="length")
    out = _openai_response_to_anthropic(resp)
    assert out.stop_reason == "max_tokens"


def test_response_malformed_tool_args() -> None:
    """tool_calls.function.arguments 가 invalid JSON 이면 _raw_args 로 wrap."""
    msg = MagicMock()
    msg.content = None
    tc = MagicMock()
    tc.id = "c1"
    tc.function = MagicMock()
    tc.function.name = "x"
    tc.function.arguments = "not-json{"
    msg.tool_calls = [tc]
    choice = MagicMock(message=msg, finish_reason="tool_calls")
    usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    resp = MagicMock(choices=[choice], usage=usage)

    out = _openai_response_to_anthropic(resp)
    assert out.content_blocks[0]["input"]["_raw_args"] == "not-json{"


# ── GrokLLM end-to-end (mock client) ────────────────────────────────────


def test_grok_llm_end_to_end_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """xAI client 를 mock 으로 갈아끼우고 전체 변환 round-trip 검증."""
    monkeypatch.setenv("XAI_API_KEY", "xai-test")

    grok = GrokLLM(model="grok-4-fast")
    # client 를 mock 으로 교체
    fake_resp = _make_openai_resp(
        content=None,
        tool_calls=[{"id": "c1", "name": "wiki_read", "args": {"path": "y.md"}}],
        finish_reason="tool_calls",
    )
    grok.client = MagicMock()
    grok.client.chat.completions.create.return_value = fake_resp

    messages = [{"role": "user", "content": "y.md 읽어줘"}]
    tools = [
        {
            "name": "wiki_read",
            "description": "read",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        }
    ]
    out = grok.call(messages=messages, tools=tools, system="당신은 Edith")
    assert out.stop_reason == "tool_use"
    assert out.content_blocks[0]["name"] == "wiki_read"

    # 호출 인자 검증 — Anthropic 포맷이 OpenAI 포맷으로 잘 변환됐는지
    call_kwargs = grok.client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "grok-4-fast"
    oai_msgs = call_kwargs["messages"]
    assert oai_msgs[0]["role"] == "system"
    assert oai_msgs[1]["role"] == "user"
    assert call_kwargs["tools"][0]["type"] == "function"
    assert call_kwargs["tool_choice"] == "auto"


def test_grok_llm_no_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        GrokLLM()


# ── get_llm() factory ──────────────────────────────────────────────────


def test_get_llm_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITH_LLM", "mock")
    llm = get_llm()
    assert llm.__class__.__name__ == "MockLLM"


def test_get_llm_grok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITH_LLM", "grok")
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    llm = get_llm()
    assert llm.__class__.__name__ == "GrokLLM"


# ── runtime + GrokLLM 통합 (mock client) ───────────────────────────────


def test_runtime_with_grok_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """harness.runtime.run() 이 GrokLLM 으로도 구동되는지 smoke check."""
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    # edith_home 골격
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")

    grok = GrokLLM(model="grok-4-fast")
    grok.client = MagicMock()
    grok.client.chat.completions.create.return_value = _make_openai_resp(
        content="hi", finish_reason="stop"
    )

    from harness.runtime import run

    trace = run("hi", edith_home=tmp_path, llm=grok)
    assert trace.finalize_reason == "end_turn"
    assert trace.output == "hi"


# 이 모듈은 LLM 응답 형식 변환 로직 테스트 — 17개 골든 케이스 회귀 체크는
# 별도 mode flag (mode: grok / mode: anthropic) 로 evals/golden/ 에서 수행.


def test_llm_response_dataclass_default() -> None:
    """LLMResponse 의 default field — 회귀 체크."""
    r = LLMResponse(stop_reason="end_turn")
    assert r.content_blocks == []
    assert r.usage_in == 0
    assert r.usage_out == 0
    assert r.text == ""
