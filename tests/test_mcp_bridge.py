"""F18 — MCP bridge 테스트.

mcp_call_fn을 inject해 래핑·forward·게이트 경계를 검증.
실 MCP client 연결은 spike의 미해결 영역 — 여기선 mock으로 추상화만 검증.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.mcp import McpToolSpec, make_mcp_tool
from harness.mcp.bridge import _no_client
from harness.state import Context, Trace
from harness.tools import Tool


def _spec(**kw: Any) -> McpToolSpec:
    base = dict(
        mcp_tool_name="mcp__claude_ai_PlayMCP__YouTubeData-get_transcripts",
        edith_tool_name="youtube_transcript",
        description="유튜브 자막 추출",
        input_schema={"type": "object", "properties": {"video_id": {"type": "string"}}},
    )
    base.update(kw)
    return McpToolSpec(**base)  # type: ignore[arg-type]


def _ctx(tmp_path: Path) -> Context:
    return Context(edith_home=tmp_path, scope="personal", trace=Trace.start("t"))


def test_make_mcp_tool_returns_edith_tool() -> None:
    tool = make_mcp_tool(_spec(), mcp_call_fn=lambda name, args: {"ok": True})
    assert isinstance(tool, Tool)
    assert tool.name == "youtube_transcript"
    assert tool.to_anthropic_spec()["name"] == "youtube_transcript"


def test_mcp_tool_forwards_to_call_fn(tmp_path: Path) -> None:
    seen: list[tuple[str, dict]] = []

    def fake(name: str, args: dict) -> Any:
        seen.append((name, args))
        return {"transcript": "안녕하세요 ..."}

    tool = make_mcp_tool(_spec(), mcp_call_fn=fake)
    result = tool.fn({"video_id": "abc"}, _ctx(tmp_path))
    assert result == {"transcript": "안녕하세요 ..."}
    assert seen == [("mcp__claude_ai_PlayMCP__YouTubeData-get_transcripts", {"video_id": "abc"})]


def test_external_write_mcp_tool_rejected() -> None:
    """external-write MCP tool은 F23 전까지 생성 거부 (R2 우회 방지)."""
    with pytest.raises(NotImplementedError, match="approval"):
        make_mcp_tool(_spec(is_external_write=True), mcp_call_fn=lambda n, a: None)


def test_default_no_client_raises(tmp_path: Path) -> None:
    """mcp_call_fn 미주입 시 호출하면 명확히 실패 (client 미연결)."""
    tool = make_mcp_tool(_spec())
    with pytest.raises(RuntimeError, match="MCP client 미연결"):
        tool.fn({"video_id": "abc"}, _ctx(tmp_path))


def test_no_client_helper_message() -> None:
    with pytest.raises(RuntimeError, match="F18 spike"):
        _no_client("mcp__x", {})


def test_mcp_tool_runs_through_runtime_gates(tmp_path: Path) -> None:
    """make_mcp_tool가 만든 tool을 registry에 넣고 runtime.run으로 호출 — 게이트 상속 확인."""
    from harness.llm import LLMResponse, MockLLM
    from harness.runtime import run
    from harness.tools import build_default_registry

    reg = build_default_registry()
    reg.register(make_mcp_tool(_spec(), mcp_call_fn=lambda n, a: {"transcript": "OK본문"}))

    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    (tmp_path / "harness" / "traces").mkdir(parents=True)

    mock = MockLLM(
        [
            LLMResponse(
                stop_reason="tool_use",
                content_blocks=[
                    {"type": "tool_use", "id": "t1", "name": "youtube_transcript",
                     "input": {"video_id": "x"}}
                ],
            ),
            LLMResponse(
                stop_reason="end_turn",
                content_blocks=[{"type": "text", "text": "정리 완료"}],
            ),
        ]
    )
    trace = run("자막 정리", edith_home=tmp_path, registry=reg, llm=mock)
    assert trace.finalize_reason == "end_turn"
    actions = [e for e in trace.events if e.kind == "action"]
    assert any(a.payload.get("tool") == "youtube_transcript" for a in actions)
    # 게이트 통과 후 observation 기록됨
    obs = [e for e in trace.events if e.kind == "observation"]
    assert any("OK본문" in str(e.payload.get("result", "")) for e in obs)
