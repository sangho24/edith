"""Phase 1 H1 smoke test — runtime이 mock LLM과 tool들을 dispatch 하는지."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.llm import LLMResponse, MockLLM
from harness.runtime import run
from harness.state import Budget
from harness.tools import build_default_registry


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    """tmp 디렉토리에 edith 골격 생성."""
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    (tmp_path / "wiki" / "entities").mkdir(parents=True)
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path


def test_smoke_end_turn_immediately(edith_home: Path) -> None:
    """LLM이 곧바로 end_turn 하면 output만 받는다."""
    mock = MockLLM(
        [
            LLMResponse(
                stop_reason="end_turn",
                content_blocks=[{"type": "text", "text": "안녕하세요"}],
                text="안녕하세요",
            ),
        ]
    )
    trace = run("간단 인사", edith_home=edith_home, llm=mock)
    assert trace.finalize_reason == "end_turn"
    assert trace.output == "안녕하세요"
    assert trace.n_steps == 1


def test_smoke_tool_use_then_end(edith_home: Path) -> None:
    """LLM이 tool 한 번 호출하고 끝낸다. capture_text가 raw에 파일을 만든다."""
    first = LLMResponse(
        stop_reason="tool_use",
        content_blocks=[
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "capture_text",
                "input": {
                    "text": "오늘 X를 메모",
                    "scope": "personal",
                    "source": "test",
                },
            }
        ],
        text="",
    )
    second = LLMResponse(
        stop_reason="end_turn",
        content_blocks=[{"type": "text", "text": "캡처 완료"}],
        text="캡처 완료",
    )
    mock = MockLLM([first, second])
    trace = run("이걸 캡처해", edith_home=edith_home, llm=mock)

    assert trace.finalize_reason == "end_turn"
    assert trace.n_steps == 2

    files = list((edith_home / "raw" / "captures").glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "오늘 X를 메모" in content
    assert "scope: personal" in content


def test_budget_steps_enforced(edith_home: Path) -> None:
    """무한 tool_use 응답 — budget steps에서 끊긴다."""
    infinite_tool = LLMResponse(
        stop_reason="tool_use",
        content_blocks=[
            {
                "type": "tool_use",
                "id": "tu_x",
                "name": "emit_log",
                "input": {"msg": "loop"},
            }
        ],
    )
    mock = MockLLM([infinite_tool] * 10)
    budget = Budget(max_tokens=999_999, max_steps=3, max_seconds=10)
    trace = run("loop", edith_home=edith_home, llm=mock, budget=budget)
    assert trace.finalize_reason == "budget_steps"
    assert trace.n_steps == 3


def test_policy_blocks_external_write(edith_home: Path) -> None:
    """gmail_send 같은 external write tool은 정책으로 차단되어야 한다.
    (등록되어 있다고 가정한 시나리오 — 지금은 등록 자체가 없음을 확인)."""
    reg = build_default_registry()
    names = {t["name"] for t in reg.all_specs()}
    assert "gmail_send" not in names
    assert "calendar_create" not in names


def test_registry_has_expected_tools() -> None:
    """기본 registry에 skill manifest의 모든 tool 등록 (P1: 9 + P3: 8 + P4: 1 + P5: 1)."""
    reg = build_default_registry()
    specs = reg.all_specs()
    assert len(specs) == 19
    names = {t["name"] for t in specs}
    expected = {
        # Phase 1 — core skill
        "wiki_read",
        "wiki_write",
        "wiki_search",
        "raw_read",
        "raw_list",
        "capture_text",
        "query_db",
        "request_approval",
        "emit_log",
        # Phase 3 F2/F3
        "calendar_today",
        "mail_triage",
        # Phase 3 F4
        "digest_latest",
        "github_workflow_get_cron",
        # Phase 3 F6/F8
        "memory_recall",
        "paper_triage",
        # Phase 3 F7/F9
        "pr_review",
        "jd_analyze",
        # Phase 4 F15 — health skill
        "health_summary",
        # Phase 5.2 F29a — mcp skill
        "recommend_mcp",
    }
    assert names == expected


def test_trace_saves_jsonl(edith_home: Path) -> None:
    """trace가 harness/traces/에 JSONL로 저장된다."""
    mock = MockLLM(
        [
            LLMResponse(
                stop_reason="end_turn",
                content_blocks=[{"type": "text", "text": "ok"}],
                text="ok",
            ),
        ]
    )
    trace = run("test", edith_home=edith_home, llm=mock)
    files = list((edith_home / "harness" / "traces").glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert '"kind": "start"' in content
    assert '"kind": "finalize"' in content
    assert trace.id in files[0].name
