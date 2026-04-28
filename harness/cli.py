"""CLI: harness run / harness traces / harness eval."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast

import click

from harness.state import Scope


def _edith_home() -> Path:
    return Path(os.environ.get("EDITH_HOME", str(Path.home() / "edith"))).resolve()


@click.group()
def main() -> None:
    """Edith harness CLI."""


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.option(
    "--scope",
    default="personal",
    type=click.Choice(["personal", "school", "work"]),
)
@click.option("--budget-tokens", default=8000, type=int)
@click.option("--budget-steps", default=20, type=int)
def run(task: tuple[str, ...], scope: str, budget_tokens: int, budget_steps: int) -> None:
    """task 실행 후 trace 요약 출력."""
    from harness.runtime import run as runtime_run
    from harness.state import Budget

    task_str = " ".join(task)
    home = _edith_home()
    if not (home / "CLAUDE.md").exists():
        click.echo(f"error: CLAUDE.md not found in {home}", err=True)
        sys.exit(1)

    budget = Budget(max_tokens=budget_tokens, max_steps=budget_steps)
    trace = runtime_run(task_str, edith_home=home, scope=cast(Scope, scope), budget=budget)

    click.echo(f"\n--- trace {trace.id} ---")
    click.echo(f"scope        : {trace.scope}")
    click.echo(f"steps        : {trace.n_steps}")
    click.echo(f"cost_tokens  : {trace.cost_tokens}")
    click.echo(f"finalize     : {trace.finalize_reason}")
    click.echo(f"\n--- output ---\n{trace.output or '(none)'}")


@main.command()
@click.option("--last", default=10, type=int, help="최근 N개")
@click.option("--grep", default=None, help="JSONL 본문 substring 매치")
@click.option("--task", "task_contains", default=None, help="task 필드에 substring 포함")
@click.option("--reason", "finalize_reason", default=None, help="finalize 사유 정확 매치")
def traces(
    last: int,
    grep: str | None,
    task_contains: str | None,
    finalize_reason: str | None,
) -> None:
    """trace 검색·요약 (H3)."""
    from harness.traces import list_traces

    home = _edith_home()
    summaries = list_traces(
        home / "harness" / "traces",
        last=last,
        grep=grep,
        task_contains=task_contains,
        finalize_reason=finalize_reason,
    )
    if not summaries:
        click.echo("no traces match")
        return
    for s in summaries:
        click.echo(str(s))


@main.command()
@click.option(
    "--golden",
    "golden_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="골든 케이스 디렉토리 (기본: $EDITH_HOME/evals/golden)",
)
@click.option("--pattern", default="*.yaml", help="case glob")
def eval(golden_dir: str | None, pattern: str) -> None:  # noqa: A001
    """golden 케이스 일괄 실행 (H4). 100% pass가 머지 기준."""
    from harness.eval import run_all

    home = _edith_home()
    gdir = Path(golden_dir) if golden_dir else home / "evals" / "golden"
    if not gdir.exists():
        click.echo(f"error: golden dir not found: {gdir}", err=True)
        sys.exit(1)

    summary = run_all(gdir, pattern=pattern)
    for r in summary.results:
        click.echo(str(r))
    click.echo("")
    click.echo(f"{summary.n_passed}/{len(summary.results)} pass")
    if not summary.all_passed:
        sys.exit(1)


@main.command()
@click.option("--window", default=24, type=int, help="시간 window (hours)")
def dash(window: int) -> None:
    """observability dashboard (H6) — 최근 window 시간 trace 통계."""
    from harness.dashboard import compute_stats

    home = _edith_home()
    stats = compute_stats(home / "harness" / "traces", window_hours=window)
    click.echo(stats.render_text())


if __name__ == "__main__":
    main()
