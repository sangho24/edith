"""H4 eval runner — golden YAML 케이스 실행 + expected 매칭."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.eval import run_all, run_case


@pytest.fixture
def golden_dir(tmp_path: Path) -> Path:
    """tmp 디렉토리에 골든 케이스 2개 생성."""
    d = tmp_path / "golden"
    d.mkdir()

    pass_yaml = """
id: pass_case
fixtures:
  identity: "# Edith\\n"
  schema: "# Schema\\n"
inputs:
  task: "간단 인사"
  scope: personal
  llm_responses:
    - stop_reason: end_turn
      text: "안녕하세요"
expected:
  finalize_reason: end_turn
  n_steps: 1
  output_contains: ["안녕"]
  tool_calls_made: 0
  policy_blocks: 0
"""
    (d / "pass.yaml").write_text(pass_yaml, encoding="utf-8")

    fail_yaml = """
id: fail_case
fixtures:
  identity: "# Edith\\n"
  schema: "# Schema\\n"
inputs:
  task: "test"
  scope: personal
  llm_responses:
    - stop_reason: end_turn
      text: "wrong output"
expected:
  finalize_reason: end_turn
  output_contains: ["존재하지않는단어"]
"""
    (d / "fail.yaml").write_text(fail_yaml, encoding="utf-8")

    return d


def test_run_case_pass(golden_dir: Path) -> None:
    result = run_case(golden_dir / "pass.yaml")
    assert result.passed
    assert result.failures == []
    assert result.case_id == "pass_case"


def test_run_case_fail(golden_dir: Path) -> None:
    result = run_case(golden_dir / "fail.yaml")
    assert not result.passed
    assert len(result.failures) >= 1
    assert "존재하지않는단어" in result.failures[0]


def test_run_all_summary(golden_dir: Path) -> None:
    summary = run_all(golden_dir)
    assert len(summary.results) == 2
    assert summary.n_passed == 1
    assert summary.n_failed == 1
    assert not summary.all_passed


def test_tool_use_case_with_files_created(tmp_path: Path) -> None:
    """tool_use → end_turn 시나리오 + files_created glob 매처."""
    d = tmp_path / "golden"
    d.mkdir()
    case_yaml = """
id: capture_case
fixtures:
  identity: "# Edith\\n"
  schema: "# Schema\\n"
inputs:
  task: "이걸 캡처해"
  scope: personal
  llm_responses:
    - stop_reason: tool_use
      content_blocks:
        - type: tool_use
          id: tu_1
          name: capture_text
          input:
            text: "test memo"
            scope: personal
            source: eval
    - stop_reason: end_turn
      text: "ok"
expected:
  finalize_reason: end_turn
  n_steps: 2
  tool_calls_made: 1
  policy_blocks: 0
  files_created:
    - "raw/captures/*.md"
"""
    (d / "capture.yaml").write_text(case_yaml, encoding="utf-8")
    result = run_case(d / "capture.yaml")
    assert result.passed, f"failures: {result.failures}"


def test_h4_eval_self_runs() -> None:
    """실제 evals/golden/h4_eval_self.yaml 파일이 통과하는지."""
    repo_root = Path(__file__).parent.parent
    case = repo_root / "evals" / "golden" / "h4_eval_self.yaml"
    if not case.exists():
        pytest.skip(f"{case} not found")
    result = run_case(case)
    assert result.passed, f"failures: {result.failures}"
