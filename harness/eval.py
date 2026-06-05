"""H4 / F20 — Eval runner.

evals/golden/*.yaml의 케이스를 일괄 실행하고 expected vs actual 검증.
새 feature는 PR에 골든 케이스 동봉 필수. 골든 100% pass 못하면 머지 거부.

케이스 종류(`kind`):
- "runtime" (기본) — runtime.run(MockLLM)으로 agent loop 실행, trace 단언.
  fixtures.register_tools로 미등록 skill의 tool을 격리 registry에 주입 가능(F20).
- "call" — runtime을 안 거치고 함수(module:attr)를 직접 호출, 반환값·예외·파일 단언.
  push ledger 카운트·suppression 같은 내부 상태를 단언하려면 이 타입 사용.
"""

from __future__ import annotations

import importlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import yaml

from harness.llm import LLMResponse, MockLLM
from harness.runtime import run
from harness.state import Budget, Scope, Trace
from harness.tools import Registry, Tool


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
    failures += _check_files(expected, home)
    return failures


def _check_files(expected: dict[str, Any], home: Path) -> list[str]:
    """files_created / files_contain 검증 (runtime·call 케이스 공용)."""
    failures: list[str] = []
    if "files_created" in expected:
        for glob_pat in expected["files_created"]:
            if not list(home.glob(glob_pat)):
                failures.append(f"expected file glob not found: {glob_pat}")
    if "files_contain" in expected:
        for relpath, needles in expected["files_contain"].items():
            # glob 지원: 매치된 첫 파일에 대해 검사
            if "*" in relpath:
                matches = list(home.glob(relpath))
                if not matches:
                    failures.append(f"files_contain: no glob match: {relpath}")
                    continue
                target = matches[0]
            else:
                target = home / relpath
                if not target.exists():
                    failures.append(f"files_contain: file not found: {relpath}")
                    continue
            content = target.read_text(encoding="utf-8")
            for needle in needles:
                if needle not in content:
                    failures.append(f"files_contain[{relpath}] missing: {needle!r}")
    return failures


def _resolve(target: str) -> Any:
    """'module.path:attr' → 실제 객체. call 케이스의 target / register_tools용."""
    if ":" not in target:
        raise ValueError(f"target must be 'module:attr', got {target!r}")
    mod_name, attr = target.split(":", 1)
    mod = importlib.import_module(mod_name)
    obj = mod
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def _sub_home(value: Any, home: Path) -> Any:
    """kwargs 값의 '$home' 토큰을 임시 home Path로 치환 (재귀)."""
    if isinstance(value, str):
        if value == "$home":
            return home
        if value.startswith("$home/"):
            return home / value[len("$home/") :]
        return value
    if isinstance(value, dict):
        return {k: _sub_home(v, home) for k, v in value.items()}
    if isinstance(value, list):
        return [_sub_home(v, home) for v in value]
    return value


def _build_registry(register_tools: list[str]) -> Registry:
    """default registry + 추가 tool(module:attr)을 등록한 격리 registry.

    code-to-skill: 아직 all_skills()에 없는 skill의 tool을 검증할 때 사용.
    """
    from harness.tools import build_default_registry

    reg = build_default_registry()
    for spec in register_tools:
        tool = _resolve(spec)
        if not isinstance(tool, Tool):
            raise TypeError(f"register_tools 항목은 Tool이어야 함: {spec}")
        reg.register(tool)
    return reg


def _check_returns(result: Any, expected: dict[str, Any]) -> list[str]:
    """call 케이스 반환값 단언: returns_equals / returns_contains / returns_truthy."""
    failures: list[str] = []
    if "returns_equals" in expected:
        if result != expected["returns_equals"]:
            failures.append(
                f"returns_equals: expected={expected['returns_equals']!r}, got={result!r}"
            )
    if "returns_contains" in expected:
        sub = expected["returns_contains"]
        if not isinstance(result, dict):
            failures.append(f"returns_contains: result is not a dict ({type(result).__name__})")
        else:
            for k, v in sub.items():
                if result.get(k) != v:
                    failures.append(f"returns_contains[{k}]: expected={v!r}, got={result.get(k)!r}")
    if "returns_truthy" in expected:
        if bool(result) != bool(expected["returns_truthy"]):
            failures.append(
                f"returns_truthy: expected {expected['returns_truthy']}, got {result!r}"
            )
    return failures


# 골든을 hermetic하게 — 개발 머신에 떠 있을 수 있는 실데이터 source override env를
# 케이스 실행 동안 제거한다(예: 실제 ds-digest URL 네트워크 호출, 실 export.xml 경로).
_HERMETIC_UNSET = (
    "EDITH_DS_DIGEST_URL",
    "EDITH_DS_DIGEST_LATEST",
    "EDITH_HEALTH_EXPORT",
    "EDITH_MAIL_FIXTURE",
    "EDITH_MAIL_BACKEND",
    "EDITH_CALENDAR_BACKEND",
)


@contextmanager
def _hermetic_env(home: Path) -> Iterator[None]:
    """케이스 실행 동안 캘린더/네트워크/실데이터 env를 격리. 종료 시 원복.

    EDITH_CALENDAR_FIXTURE를 임시 home의 events.json으로 강제 → macOS에서도 EventKit
    (실제 Apple Calendar)을 읽지 않고 fixture만 본다. 골든이 머신 상태에 의존하지 않게 한다.
    """
    saved: dict[str, str | None] = {k: os.environ.pop(k, None) for k in _HERMETIC_UNSET}
    saved["EDITH_CALENDAR_FIXTURE"] = os.environ.get("EDITH_CALENDAR_FIXTURE")
    os.environ["EDITH_CALENDAR_FIXTURE"] = str(home / "raw" / "calendar" / "events.json")
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_case(yaml_path: Path) -> EvalResult:
    """단일 골든 케이스를 실행. kind=runtime(기본) 또는 call."""
    case = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    case_id = case.get("id", yaml_path.stem)
    kind = case.get("kind", "runtime")
    fixtures = case.get("fixtures", {})
    inputs = case.get("inputs", {})
    expected = case.get("expected", {})

    t0 = time.time()
    with TemporaryDirectory() as tmp:
        home = Path(tmp)
        _setup_fixtures(home, fixtures)

        with _hermetic_env(home):
            if kind == "call":
                return _run_call_case(case_id, case, inputs, expected, home, t0)

            # kind == "runtime"
            responses = [_build_response(r) for r in inputs.get("llm_responses", [])]
            mock = MockLLM(responses)

            budget = Budget(
                max_tokens=inputs.get("budget_tokens", 8000),
                max_steps=inputs.get("budget_steps", 20),
                max_seconds=inputs.get("budget_seconds", 30.0),
            )

            # F20 — 미등록 skill의 tool을 격리 registry에 주입해 검증 (code-to-skill).
            register_tools = fixtures.get("register_tools")
            registry = _build_registry(register_tools) if register_tools else None

            try:
                trace = run(
                    inputs.get("task", ""),
                    edith_home=home,
                    scope=cast(Scope, inputs.get("scope", "personal")),
                    budget=budget,
                    registry=registry,
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


def _run_call_case(
    case_id: str,
    case: dict[str, Any],
    inputs: dict[str, Any],
    expected: dict[str, Any],
    home: Path,
    t0: float,
) -> EvalResult:
    """kind=call — 함수(module:attr)를 직접 호출, 반환값/예외/파일 단언.

    inputs.target: 'module:attr', inputs.kwargs: 호출 kwargs ('$home' 토큰 치환).
    expected.raises: 예외 클래스명 substring. expected.returns_*: 반환값 단언.
    """
    target = case.get("target") or inputs.get("target")
    if not target:
        return EvalResult(case_id, False, ["call 케이스에 target('module:attr') 필요"],
                          (time.time() - t0) * 1000)

    kwargs = _sub_home(inputs.get("kwargs", {}), home)
    try:
        fn = _resolve(target)
    except Exception as e:
        return EvalResult(case_id, False, [f"target resolve 실패: {e}"],
                          (time.time() - t0) * 1000)

    failures: list[str] = []
    result: Any = None
    try:
        result = fn(**kwargs)
    except Exception as e:
        want = expected.get("raises")
        if want and want in type(e).__name__:
            # 예상된 예외 — 파일 단언만 추가 검사
            failures += _check_files(expected, home)
            return EvalResult(case_id, not failures, failures, (time.time() - t0) * 1000)
        return EvalResult(case_id, False, [f"call raised {type(e).__name__}: {e}"],
                          (time.time() - t0) * 1000)

    if expected.get("raises"):
        failures.append(f"expected raises {expected['raises']!r} but call returned {result!r}")
    failures += _check_returns(result, expected)
    failures += _check_files(expected, home)
    return EvalResult(case_id, not failures, failures, (time.time() - t0) * 1000)


def run_all(golden_dir: Path, pattern: str = "*.yaml") -> EvalSummary:
    """golden_dir 안 모든 YAML 케이스 실행."""
    summary = EvalSummary()
    for yaml_path in sorted(golden_dir.glob(pattern)):
        summary.results.append(run_case(yaml_path))
    return summary
