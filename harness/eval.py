"""H4 — Eval runner.

evals/golden/*.yaml의 케이스를 일괄 실행하고 expected vs actual 검증.
새 feature는 PR에 골든 케이스 동봉 필수. 골든 100% pass 못하면 머지 거부.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import yaml

from harness.llm import LLMResponse, MockLLM
from harness.runtime import run
from harness.state import Budget, Scope, Trace


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    cost_tokens: int = 0

    def __str__(self) -> str:
        mark = "✓" if self.passed else "✗"
        head = f"{mark} {self.case_id} ({self.duration_ms:.0f}ms, {self.cost_tokens} tok)"
        if self.failures:
            return head + "\n  - " + "\n  - ".join(self.failures)
        return head


@dataclass
class EvalSummary:
    results: list[EvalResult] = field(default_factory=list)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def n_failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def all_passed(self) -> bool:
        return self.n_failed == 0


def _build_response(d: dict[str, Any]) -> LLMResponse:
    """YAML 딕셔너리를 LLMResponse로. text만 있으면 content_blocks 자동 derive."""
    if "content_blocks" not in d and "text" in d:
        d = {**d, "content_blocks": [{"type": "text", "text": d["text"]}]}
    return LLMResponse(
        stop_reason=d.get("stop_reason", "end_turn"),
        content_blocks=d.get("content_blocks", []),
        text=d.get("text", ""),
        usage_in=d.get("usage_in", 0),
        usage_out=d.get("usage_out", 0),
    )


def _setup_fixtures(home: Path, fixtures: dict[str, Any]) -> None:
    """case.fixtures 에 따라 tmp 디렉토리 셋업."""
    (home / "raw" / "captures").mkdir(parents=True, exist_ok=True)
    (home / "wiki").mkdir(parents=True, exist_ok=True)
    (home / "harness" / "traces").mkdir(parents=True, exist_ok=True)
    (home / "identity.md").write_text(fixtures.get("identity", "# Edith\n"), encoding="utf-8")
    (home / "CLAUDE.md").write_text(fixtures.get("schema", "# Schema\n"), encoding="utf-8")
    for relpath, content in fixtures.get("raw_files", {}).items():
        target = home / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for relpath, content in fixtures.get("wiki_files", {}).items():
        target = home / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _check_expected(trace: Trace, expected: dict[str, Any], home: Path) -> list[str]:
    """expected vs actual. 실패한 항목 list 반환 (빈 list = pass)."""
    failures: list[str] = []

    if "finalize_reason" in expected:
        if trace.finalize_reason != expected["finalize_reason"]:
            failures.append(
                f"finalize_reason: expected={expected['finalize_reason']!r}, "
                f"got={trace.finalize_reason!r}"
            )
    if "n_steps" in expected:
        if trace.n_steps != expected["n_steps"]:
            failures.append(f"n_steps: expected={expected['n_steps']}, got={trace.n_steps}")
    if "output_contains" in expected:
        out = trace.output or ""
        for needle in expected["output_contains"]:
            if needle not in out:
                failures.append(f"output missing substring: {needle!r}")

    n_actions = sum(1 for e in trace.events if e.kind == "action")
    n_blocked = sum(1 for e in trace.events if e.kind == "blocked")

    if "tool_calls_made" in expected:
        if n_actions != expected["tool_calls_made"]:
            failures.append(
                f"tool_calls_made: expected={expected['tool_calls_made']}, got={n_actions}"
            )
    if "policy_blocks" in expected:
        if n_blocked != expected["policy_blocks"]:
            failures.append(f"policy_blocks: expected={expected['policy_blocks']}, got={n_blocked}")
    if "files_created" in expected:
        for glob_pat in expected["files_created"]:
            if not list(home.glob(glob_pat)):
                failures.append(f"expected file glob not found: {glob_pat}")

    return failures


def run_case(yaml_path: Path) -> EvalResult:
    """단일 골든 케이스를 실행."""
    case = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    case_id = case.get("id", yaml_path.stem)
    fixtures = case.get("fixtures", {})
    inputs = case.get("inputs", {})
    expected = case.get("expected", {})

    t0 = time.time()
    with TemporaryDirectory() as tmp:
        home = Path(tmp)
        _setup_fixtures(home, fixtures)

        responses = [_build_response(r) for r in inputs.get("llm_responses", [])]
        mock = MockLLM(responses)

        budget = Budget(
            max_tokens=inputs.get("budget_tokens", 8000),
            max_steps=inputs.get("budget_steps", 20),
            max_seconds=inputs.get("budget_seconds", 30.0),
        )

        try:
            trace = run(
                inputs.get("task", ""),
                edith_home=home,
                scope=cast(Scope, inputs.get("scope", "personal")),
                budget=budget,
                llm=mock,
            )
        except Exception as e:
            return EvalResult(
                case_id=case_id,
                passed=False,
                failures=[f"runtime exception: {type(e).__name__}: {e}"],
                duration_ms=(time.time() - t0) * 1000,
            )

        failures = _check_expected(trace, expected, home)
        return EvalResult(
            case_id=case_id,
            passed=not failures,
            failures=failures,
            duration_ms=(time.time() - t0) * 1000,
            cost_tokens=trace.cost_tokens,
        )


def run_all(golden_dir: Path, pattern: str = "*.yaml") -> EvalSummary:
    """golden_dir 안 모든 YAML 케이스 실행."""
    summary = EvalSummary()
    for yaml_path in sorted(golden_dir.glob(pattern)):
        summary.results.append(run_case(yaml_path))
    return summary
