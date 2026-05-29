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


# ── F20 — kind:call 케이스 + registry injection ──────────────────────────


def _write(d: Path, name: str, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def test_call_case_returns_contains(tmp_path: Path) -> None:
    case = _write(
        tmp_path / "g",
        "c.yaml",
        """
id: call_rc
kind: call
target: harness.integrations.github_workflow:read_workflow
fixtures:
  raw_files:
    "wf.yml": "name: demoX\\n"
inputs:
  kwargs:
    workflow_path: "$home/wf.yml"
expected:
  returns_contains:
    name: demoX
""",
    )
    result = run_case(case)
    assert result.passed, result.failures


def test_call_case_returns_contains_mismatch_fails(tmp_path: Path) -> None:
    case = _write(
        tmp_path / "g",
        "c.yaml",
        """
id: call_mismatch
kind: call
target: harness.integrations.github_workflow:read_workflow
fixtures:
  raw_files:
    "wf.yml": "name: actual\\n"
inputs:
  kwargs:
    workflow_path: "$home/wf.yml"
expected:
  returns_contains:
    name: expected_other
""",
    )
    result = run_case(case)
    assert not result.passed
    assert any("returns_contains" in f for f in result.failures)


def test_call_case_raises(tmp_path: Path) -> None:
    case = _write(
        tmp_path / "g",
        "c.yaml",
        """
id: call_raises
kind: call
target: harness.eval:_resolve
inputs:
  kwargs:
    target: "no_colon"
expected:
  raises: ValueError
""",
    )
    result = run_case(case)
    assert result.passed, result.failures


def test_call_case_raises_but_returned_fails(tmp_path: Path) -> None:
    case = _write(
        tmp_path / "g",
        "c.yaml",
        """
id: call_no_raise
kind: call
target: harness.integrations.github_workflow:read_workflow
fixtures:
  raw_files:
    "wf.yml": "name: x\\n"
inputs:
  kwargs:
    workflow_path: "$home/wf.yml"
expected:
  raises: ValueError
""",
    )
    result = run_case(case)
    assert not result.passed
    assert any("expected raises" in f for f in result.failures)


def test_call_case_missing_target_fails(tmp_path: Path) -> None:
    case = _write(tmp_path / "g", "c.yaml", "id: no_target\nkind: call\ninputs: {}\n")
    result = run_case(case)
    assert not result.passed
    assert any("target" in f for f in result.failures)


def test_build_registry_injects_unregistered_tool() -> None:
    """F20 — register_tools가 default에 없는 tool을 격리 registry에 추가."""
    from harness import eval as eval_mod
    from harness.tools import Tool, build_default_registry

    base = len(build_default_registry().all_specs())
    # default에 없는 신규 tool을 임시 모듈 속성으로 노출 후 주입
    eval_mod._EVAL_FIXTURE_TOOL = Tool(  # type: ignore[attr-defined]
        name="eval_fixture_only",
        description="test-only",
        input_schema={"type": "object", "properties": {}},
        fn=lambda args, ctx: {"ok": True},
    )
    try:
        reg = eval_mod._build_registry(["harness.eval:_EVAL_FIXTURE_TOOL"])
        names = {s["name"] for s in reg.all_specs()}
        assert "eval_fixture_only" in names
        assert len(reg.all_specs()) == base + 1
    finally:
        del eval_mod._EVAL_FIXTURE_TOOL  # type: ignore[attr-defined]


def test_call_case_files_created(tmp_path: Path) -> None:
    """call 케이스도 files_created 단언 가능."""
    case = _write(
        tmp_path / "g",
        "c.yaml",
        """
id: call_files
kind: call
target: harness.integrations.github_workflow:set_cron
fixtures:
  raw_files:
    "wf.yml": |
      on:
        schedule:
          - cron: '10 22 * * *'
inputs:
  kwargs:
    workflow_path: "$home/wf.yml"
    new_cron: "0 13 * * *"
expected:
  files_contain:
    "wf.yml": ["0 13 * * *"]
""",
    )
    result = run_case(case)
    assert result.passed, result.failures
