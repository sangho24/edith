"""Phase 2 W1 — compile pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.compile import _find_uncompiled, _load_log, compile_raw, infer_scope
from harness.llm import LLMResponse, MockLLM


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    (tmp_path / "raw" / "papers").mkdir(parents=True)
    (tmp_path / "wiki" / "entities").mkdir(parents=True)
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path


def test_infer_scope_work() -> None:
    assert infer_scope("raw/work_meeting.md") == "work"
    assert infer_scope("raw/captures/note.md", "삼일PwC 클라이언트 미팅") == "work"


def test_infer_scope_school() -> None:
    assert infer_scope("raw/school/lecture_01.md") == "school"
    assert infer_scope("raw/captures/x.md", "오늘 강의 과제") == "school"


def test_infer_scope_personal_default() -> None:
    assert infer_scope("raw/captures/random.md") == "personal"
    assert infer_scope("raw/captures/x.md", "그냥 메모") == "personal"


def test_find_uncompiled_empty(edith_home: Path) -> None:
    new_files = _find_uncompiled(edith_home, {})
    assert new_files == []


def test_find_uncompiled_with_files(edith_home: Path) -> None:
    (edith_home / "raw/captures/test1.md").write_text("hello")
    (edith_home / "raw/papers/p1.md").write_text("paper")
    new_files = _find_uncompiled(edith_home, {})
    assert len(new_files) == 2
    assert "raw/captures/test1.md" in new_files
    assert "raw/papers/p1.md" in new_files


def test_find_uncompiled_skips_already_compiled(edith_home: Path) -> None:
    (edith_home / "raw/captures/test1.md").write_text("hello")
    (edith_home / "raw/captures/test2.md").write_text("world")
    log = {"raw/captures/test1.md": {"compiled_at": "2026-04-28"}}
    new_files = _find_uncompiled(edith_home, log)
    assert new_files == ["raw/captures/test2.md"]


def test_find_uncompiled_skips_gitkeep(edith_home: Path) -> None:
    (edith_home / "raw/captures/.gitkeep").write_text("")
    new_files = _find_uncompiled(edith_home, {})
    assert new_files == []


def test_dry_run(edith_home: Path) -> None:
    (edith_home / "raw/captures/test.md").write_text("# Test")
    result = compile_raw(edith_home, llm=MockLLM(), dry_run=True)
    assert result.new_files == ["raw/captures/test.md"]
    assert result.compiled == []
    # log not written
    assert not (edith_home / "harness/compile_log.json").exists()


def test_compile_one_file_success(edith_home: Path) -> None:
    (edith_home / "raw/captures/test.md").write_text("오늘 김교수님과 미팅. ICLR 2026 area chair.")
    mock = MockLLM(
        [
            # step 1: raw_read
            LLMResponse(
                stop_reason="tool_use",
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "raw_read",
                        "input": {"path": "raw/captures/test.md"},
                    }
                ],
            ),
            # step 2: wiki_write
            LLMResponse(
                stop_reason="tool_use",
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "tu_2",
                        "name": "wiki_write",
                        "input": {
                            "path": "wiki/entities/김교수.md",
                            "content": "# 김교수\n\nICLR 2026 area chair.",
                            "support_refs": ["raw/captures/test.md"],
                        },
                    }
                ],
            ),
            # step 3: end_turn
            LLMResponse(stop_reason="end_turn", text="entities/김교수.md 1 fact 추가"),
        ]
    )
    result = compile_raw(edith_home, llm=mock)

    assert "raw/captures/test.md" in result.compiled
    assert result.failed == []

    # wiki/entities/김교수.md 생성됨 (frontmatter는 H7이 자동 prepend)
    written = (edith_home / "wiki/entities/김교수.md").read_text(encoding="utf-8")
    assert "type: entity" in written
    assert "ICLR 2026 area chair" in written

    # compile_log 저장됨. content에 "교수" 키워드가 있어서 scope=school로 분류됨.
    log_path = edith_home / "harness/compile_log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert "raw/captures/test.md" in log
    assert log["raw/captures/test.md"]["scope"] == "school"


def test_compile_log_persists_across_runs(edith_home: Path) -> None:
    """첫 run에서 컴파일된 파일은 두 번째 run에서 skip."""
    (edith_home / "raw/captures/a.md").write_text("a")

    mock1 = MockLLM([LLMResponse(stop_reason="end_turn", text="done")])
    result1 = compile_raw(edith_home, llm=mock1)
    assert result1.compiled == ["raw/captures/a.md"]

    # 두 번째 run — 새 파일 없음
    mock2 = MockLLM([])
    result2 = compile_raw(edith_home, llm=mock2)
    assert result2.new_files == []
    assert result2.compiled == []


def test_compile_failure_recorded(edith_home: Path) -> None:
    """LLM이 budget 초과 등으로 end_turn 못하면 failed에 기록."""
    (edith_home / "raw/captures/b.md").write_text("b")
    # MockLLM이 응답 없음 → "(mock done)" 으로 end_turn 떨어짐 → 성공 케이스
    # failure 시뮬: tool_use만 무한 반복하다 budget_steps에서 끊김
    inf_tool = LLMResponse(
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
    mock = MockLLM([inf_tool] * 30)
    result = compile_raw(edith_home, llm=mock)
    # budget_steps로 finalize → failed
    assert result.compiled == []
    assert len(result.failed) == 1
    rel, reason = result.failed[0]
    assert rel == "raw/captures/b.md"
    assert "budget_steps" in reason


def test_load_log_missing(edith_home: Path) -> None:
    log = _load_log(edith_home / "harness/compile_log.json")
    assert log == {}


def test_load_log_corrupt(edith_home: Path) -> None:
    p = edith_home / "harness/compile_log.json"
    p.write_text("{not valid json")
    log = _load_log(p)
    assert log == {}
