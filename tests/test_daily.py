"""Phase 2 W3 — daily loop tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.daily import daily_loop
from harness.llm import LLMResponse, MockLLM


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "wiki" / "log.md").write_text("# Compile Log\n\n(empty)\n", encoding="utf-8")
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "evals" / "golden").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path


def test_daily_no_raw_no_eval(edith_home: Path) -> None:
    """raw 비어있고 golden 케이스 없음 — 무사 통과."""
    result = daily_loop(edith_home, llm=MockLLM())
    assert result.compile_result.new_files == []
    assert result.eval_summary.n_passed == 0
    assert len(result.eval_summary.results) == 0
    assert not result.failed
    assert result.log_appended  # log.md 존재해서 append 됨


def test_daily_log_md_appended(edith_home: Path) -> None:
    result = daily_loop(edith_home, llm=MockLLM())
    log = (edith_home / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "daily report" in log
    assert "컴파일" in log
    assert "24h" in log
    assert result.log_appended


def test_daily_with_compile_success(edith_home: Path) -> None:
    """raw 1개 + MockLLM이 end_turn 즉시 — 컴파일 성공."""
    (edith_home / "raw" / "captures" / "x.md").write_text("hello", encoding="utf-8")
    mock = MockLLM([LLMResponse(stop_reason="end_turn", text="done")])
    result = daily_loop(edith_home, llm=mock)
    assert "raw/captures/x.md" in result.compile_result.compiled
    assert not result.failed


def test_daily_with_eval_pass(edith_home: Path) -> None:
    """golden case 1개 + 통과 시나리오."""
    case_yaml = """
id: dummy_pass
fixtures:
  identity: "# Edith\\n"
  schema: "# Schema\\n"
inputs:
  task: "test"
  scope: personal
  llm_responses:
    - stop_reason: end_turn
      text: "ok"
expected:
  finalize_reason: end_turn
"""
    (edith_home / "evals" / "golden" / "dummy.yaml").write_text(case_yaml, encoding="utf-8")
    result = daily_loop(edith_home, llm=MockLLM())
    assert len(result.eval_summary.results) == 1
    assert result.eval_summary.n_passed == 1
    assert result.eval_pass_rate == 1.0
    assert not result.failed


def test_daily_with_eval_failure_marks_failed(edith_home: Path) -> None:
    """golden 실패 → daily.failed = True."""
    case_yaml = """
id: dummy_fail
fixtures:
  identity: "# Edith\\n"
  schema: "# Schema\\n"
inputs:
  task: "test"
  scope: personal
  llm_responses:
    - stop_reason: end_turn
      text: "wrong"
expected:
  finalize_reason: end_turn
  output_contains: ["존재하지않음"]
"""
    (edith_home / "evals" / "golden" / "dummy.yaml").write_text(case_yaml, encoding="utf-8")
    result = daily_loop(edith_home, llm=MockLLM())
    assert result.eval_summary.n_failed == 1
    assert result.failed

    log = (edith_home / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "dummy_fail" in log


def test_daily_render_text(edith_home: Path) -> None:
    result = daily_loop(edith_home, llm=MockLLM())
    rendered = result.render_text()
    assert "Edith daily report" in rendered
    assert "compile" in rendered
    assert "eval" in rendered
    assert "24h trace" in rendered


def test_daily_no_log_md_does_not_crash(edith_home: Path) -> None:
    """wiki/log.md 가 없어도 daily는 동작 (log_appended=False)."""
    (edith_home / "wiki" / "log.md").unlink()
    result = daily_loop(edith_home, llm=MockLLM())
    assert not result.log_appended
    assert not result.failed
