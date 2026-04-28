"""Phase 2 W3 — Daily compile loop.

매일 22시 cron/launchd가 실행하는 통합 루틴:
1. compile_raw — 새 raw → wiki
2. eval (golden) — regression check (1개라도 실패하면 daily.failed=True)
3. dashboard — 24h 통계
4. wiki/log.md 에 그날 변경 요약 append
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from harness.compile import CompileResult, compile_raw
from harness.dashboard import DashboardStats, compute_stats
from harness.eval import EvalSummary, run_all
from harness.llm import AnthropicLLM, MockLLM


@dataclass
class DailyResult:
    started_at: str
    compile_result: CompileResult = field(default_factory=CompileResult)
    eval_summary: EvalSummary = field(default_factory=EvalSummary)
    stats: DashboardStats = field(default_factory=lambda: DashboardStats(window_hours=24))
    log_appended: bool = False
    failed: bool = False

    @property
    def eval_pass_rate(self) -> float:
        n = len(self.eval_summary.results)
        return self.eval_summary.n_passed / n if n else 1.0

    def render_text(self) -> str:
        lines = [
            "─" * 50,
            f"Edith daily report · {self.started_at[:10]}",
            "─" * 50,
            f"compile  : new {len(self.compile_result.new_files)}, "
            f"ok {len(self.compile_result.compiled)}, "
            f"fail {len(self.compile_result.failed)}",
        ]
        n_eval = len(self.eval_summary.results)
        if n_eval:
            lines.append(
                f"eval     : {self.eval_summary.n_passed}/{n_eval} pass "
                f"({self.eval_pass_rate * 100:.0f}%)"
            )
            if self.eval_summary.n_failed:
                failed_ids = ", ".join(r.case_id for r in self.eval_summary.results if not r.passed)
                lines.append(f"  failed: {failed_ids}")
        else:
            lines.append("eval     : (no golden cases)")
        lines.append(
            f"24h trace: {self.stats.n_runs} runs, "
            f"{self.stats.n_errors} errors, "
            f"{self.stats.n_policy_blocks} blocks, "
            f"{self.stats.total_cost_tokens} tok"
        )
        lines.append(f"failed   : {self.failed}")
        return "\n".join(lines)


def _append_log(edith_home: Path, result: DailyResult) -> bool:
    log_path = edith_home / "wiki" / "log.md"
    if not log_path.exists():
        return False
    today = result.started_at[:10]
    cr = result.compile_result
    block = [
        f"\n## {today} daily report",
        f"- 컴파일: new {len(cr.new_files)} / ok {len(cr.compiled)} / fail {len(cr.failed)}",
    ]
    n_eval = len(result.eval_summary.results)
    if n_eval:
        block.append(
            f"- Eval: {result.eval_summary.n_passed}/{n_eval} pass "
            f"({result.eval_pass_rate * 100:.0f}%)"
        )
        if result.eval_summary.n_failed:
            failed_ids = ", ".join(r.case_id for r in result.eval_summary.results if not r.passed)
            block.append(f"  - failed: {failed_ids}")
    block.append(
        f"- 24h: {result.stats.n_runs} runs · "
        f"{result.stats.n_errors} errors · "
        f"{result.stats.n_policy_blocks} blocks · "
        f"{result.stats.total_cost_tokens} tok"
    )
    log_path.write_text(
        log_path.read_text(encoding="utf-8") + "\n".join(block) + "\n",
        encoding="utf-8",
    )
    return True


def daily_loop(
    edith_home: Path,
    llm: AnthropicLLM | MockLLM | None = None,
    eval_dir: Path | None = None,
) -> DailyResult:
    """하루 한 번 실행할 통합 루틴."""
    started_at = datetime.now(UTC).isoformat()
    result = DailyResult(started_at=started_at)

    # 1. compile
    result.compile_result = compile_raw(edith_home, llm=llm)

    # 2. eval (regression check)
    eval_dir = eval_dir or (edith_home / "evals" / "golden")
    if eval_dir.exists() and any(eval_dir.glob("*.yaml")):
        result.eval_summary = run_all(eval_dir)

    # 3. dashboard
    result.stats = compute_stats(edith_home / "harness" / "traces", window_hours=24)

    # 4. log append
    result.log_appended = _append_log(edith_home, result)

    # failed 판정: compile failures OR eval regressions
    result.failed = bool(result.compile_result.failed) or result.eval_summary.n_failed > 0

    return result
