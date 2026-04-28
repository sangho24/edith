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


@main.command()
@click.option("--dry-run", is_flag=True, help="실행 안 하고 새 파일 list만")
def compile(dry_run: bool) -> None:  # noqa: A001
    """raw → wiki LLM 컴파일 (Phase 2 W1)."""
    from harness.compile import compile_raw

    home = _edith_home()
    result = compile_raw(home, dry_run=dry_run)
    click.echo(result.render_text())
    if result.failed:
        sys.exit(1)


@main.command()
def daily() -> None:
    """daily loop (Phase 2 W3) — compile + eval + dashboard + log.md append."""
    from harness.daily import daily_loop

    home = _edith_home()
    result = daily_loop(home)
    click.echo(result.render_text())
    if result.failed:
        sys.exit(1)


@main.command()
@click.argument("text", nargs=-1, required=True)
@click.option(
    "--scope",
    default=None,
    type=click.Choice(["personal", "school", "work"]),
    help="명시 안 하면 자동 분류",
)
@click.option("--source", default="manual", help="frontmatter source 필드")
@click.option(
    "--via-llm",
    is_flag=True,
    help="runtime/LLM 통과 (trace 기록, wiki 즉시 통합 가능)",
)
def cap(text: tuple[str, ...], scope: str | None, source: str, via_llm: bool) -> None:
    """Quick capture (Phase 3 F1) — 텍스트를 raw/captures/에 저장."""
    from harness.capture import capture_to_raw

    home = _edith_home()
    result = capture_to_raw(
        text=" ".join(text),
        edith_home=home,
        scope=cast(Scope, scope) if scope else None,
        source=source,
        via_llm=via_llm,
    )
    if result.ok:
        click.echo(f"✓ {result.path} (scope={result.scope})")
        if result.trace_id:
            click.echo(f"  trace: {result.trace_id}")
    else:
        click.echo(f"✗ {result.error or 'failed'}", err=True)
        sys.exit(1)


@main.command()
@click.option(
    "--fixture",
    default=None,
    type=click.Path(),
    help="events.json 경로 (default: $EDITH_HOME/raw/calendar/events.json)",
)
def today(fixture: str | None) -> None:
    """오늘 캘린더 일정 (Phase 3 F2)."""
    from harness.calendar import LocalCalendarSource, render_today, today_view

    home = _edith_home()
    fixture_path = Path(fixture) if fixture else home / "raw" / "calendar" / "events.json"
    source = LocalCalendarSource(fixture_path)
    view = today_view(source)
    click.echo(render_today(view))


@main.command()
@click.option(
    "--fixture",
    default=None,
    type=click.Path(),
    help="messages.json 경로 (default: $EDITH_HOME/raw/mail/messages.json)",
)
@click.option("--limit", default=50, type=int)
def mail(fixture: str | None, limit: int) -> None:
    """unread 메일 priority triage (Phase 3 F3)."""
    from harness.mail import LocalMessageSource, render_triage
    from harness.mail import triage as triage_fn

    home = _edith_home()
    fixture_path = Path(fixture) if fixture else home / "raw" / "mail" / "messages.json"
    source = LocalMessageSource(fixture_path)
    items = triage_fn(source.list_unread(limit=limit))
    click.echo(render_triage(items))


@main.command()
def brief() -> None:
    """Morning Briefing (Phase 3 F4) — 오늘 일정 + 메일 + ds-digest + Top 3."""
    from harness.morning import compose_brief

    home = _edith_home()
    b = compose_brief(home)
    click.echo(b.render_text())


@main.group("approve")
def approve_group() -> None:
    """approval queue 관리 (F5) — list / yes / no / show."""


@approve_group.command("list")
@click.option(
    "--status",
    default="pending",
    type=click.Choice(["pending", "approved", "rejected", "expired", "executed", "all"]),
)
def approve_list(status: str) -> None:
    """승인 큐 목록 (default: pending)."""
    from harness.approval import ApprovalQueue

    home = _edith_home()
    queue = ApprovalQueue(home / "harness" / "approvals.json")
    queue.expire_old()
    items = queue.list(status=None if status == "all" else status)  # type: ignore[arg-type]
    if not items:
        click.echo(f"({status}) 항목 없음")
        return
    for r in items:
        risk = "❗" if r.risk_score >= 8 else ("⚠️" if r.risk_score >= 5 else "·")
        rev = "↩" if r.reversible else "🔒"
        click.echo(f"{risk}{rev} [{r.status}] {r.id} · {r.action_type} → {r.target_system}")
        click.echo(f"   {r.preview[:80]}")
        click.echo(f"   expires: {r.expires_at}")


@approve_group.command("show")
@click.argument("id_")
def approve_show(id_: str) -> None:
    """approval 상세."""
    from harness.approval import ApprovalQueue

    queue = ApprovalQueue(_edith_home() / "harness" / "approvals.json")
    r = queue.get(id_)
    if r is None:
        click.echo(f"not found: {id_}", err=True)
        sys.exit(1)
    click.echo(f"id            : {r.id}")
    click.echo(f"action_type   : {r.action_type}")
    click.echo(f"target_system : {r.target_system}")
    click.echo(f"status        : {r.status}")
    click.echo(f"risk_score    : {r.risk_score}/10")
    click.echo(f"reversible    : {r.reversible}")
    click.echo(f"requested_at  : {r.requested_at}")
    click.echo(f"expires_at    : {r.expires_at}")
    if r.approved_by:
        click.echo(f"approved_by   : {r.approved_by}")
    if r.executed_at:
        click.echo(f"executed_at   : {r.executed_at}")
    click.echo("--- preview ---")
    click.echo(r.preview)


@approve_group.command("yes")
@click.argument("id_")
def approve_yes(id_: str) -> None:
    """approve. status: pending → approved. executor는 feature별 별도 실행."""
    from harness.approval import ApprovalQueue

    queue = ApprovalQueue(_edith_home() / "harness" / "approvals.json")
    try:
        r = queue.approve(id_)
    except (KeyError, ValueError) as e:
        click.echo(f"✗ {e}", err=True)
        sys.exit(1)
    click.echo(f"✓ approved {r.id} ({r.action_type})")
    click.echo("  executor가 실제 action 실행 후 `mark_executed` 호출 필요.")


@approve_group.command("no")
@click.argument("id_")
def approve_no(id_: str) -> None:
    """reject. status: pending/approved → rejected."""
    from harness.approval import ApprovalQueue

    queue = ApprovalQueue(_edith_home() / "harness" / "approvals.json")
    try:
        r = queue.reject(id_)
    except (KeyError, ValueError) as e:
        click.echo(f"✗ {e}", err=True)
        sys.exit(1)
    click.echo(f"✗ rejected {r.id} ({r.action_type})")


@main.command()
@click.argument("query", nargs=-1, required=True)
@click.option("--top-k", default=10, type=int)
def recall(query: tuple[str, ...], top_k: int) -> None:
    """Memory recall (F6) — wiki + raw에서 query 검색."""
    from harness.recall import recall as recall_fn
    from harness.recall import render_recall

    q = " ".join(query)
    hits = recall_fn(q, _edith_home(), top_k=top_k)
    click.echo(render_recall(hits, q))


@main.command()
@click.argument("arxiv_input")
def paper(arxiv_input: str) -> None:
    """Paper triage (F8) — arxiv URL/ID → 메타데이터 + wiki summary path 제안."""
    from harness.integrations.arxiv import fetch_arxiv_metadata, parse_arxiv_id

    arxiv_id = parse_arxiv_id(arxiv_input)
    if not arxiv_id:
        click.echo(f"✗ arxiv id를 파싱할 수 없습니다: {arxiv_input}", err=True)
        sys.exit(1)
    try:
        meta = fetch_arxiv_metadata(arxiv_id)
    except Exception as e:
        click.echo(f"✗ fetch error: {e}", err=True)
        sys.exit(1)
    if not meta:
        click.echo("✗ arxiv API에서 entry 못 찾음", err=True)
        sys.exit(1)
    click.echo(f"id       : {meta['id']}")
    click.echo(f"title    : {meta['title']}")
    click.echo(f"authors  : {', '.join(meta['authors'][:5])}")
    click.echo(f"category : {meta.get('primary_category', '')}")
    click.echo("\n--- abstract ---")
    click.echo(meta["abstract"][:600])
    click.echo(f"\nsuggested wiki: wiki/summaries/arxiv_{meta['id'].replace('.', '_')}.md")


@main.group("gh-cron")
def gh_cron() -> None:
    """GitHub Actions workflow cron 관리 (read · write CLI)."""


@gh_cron.command("get")
@click.option(
    "--workflow",
    "workflow_path",
    default=None,
    type=click.Path(),
    help="workflow YAML 경로 (default: $EDITH_DS_DIGEST_WORKFLOW)",
)
def gh_cron_get(workflow_path: str | None) -> None:
    """workflow의 cron 조회 (KST 자동 변환)."""
    from harness.integrations.github_workflow import get_crons, parse_cron_to_kst

    path = Path(workflow_path).expanduser() if workflow_path else _resolve_workflow()
    if not path.exists():
        click.echo(f"error: workflow not found: {path}", err=True)
        sys.exit(1)
    crons = get_crons(path)
    if not crons:
        click.echo(f"{path}: cron schedule 없음")
        return
    click.echo(f"{path}")
    for i, c in enumerate(crons):
        kst = parse_cron_to_kst(c)
        kst_str = f" (KST {kst[0]:02d}:{kst[1]:02d})" if kst else ""
        click.echo(f"  [{i}] {c}{kst_str}")


@gh_cron.command("set")
@click.option(
    "--workflow",
    "workflow_path",
    default=None,
    type=click.Path(),
    help="workflow YAML 경로 (default: $EDITH_DS_DIGEST_WORKFLOW)",
)
@click.option(
    "--time",
    "kst_time",
    required=True,
    help="KST 시각 'HH:MM' 형식 (예: 08:00)",
)
@click.option("--idx", default=0, type=int, help="여러 cron 있을 때 idx (default 0)")
@click.option("--yes", is_flag=True, help="확인 prompt skip")
def gh_cron_set(workflow_path: str | None, kst_time: str, idx: int, yes: bool) -> None:
    """workflow의 cron을 KST 시각 기준으로 변경 (UTC 자동 변환)."""
    from harness.integrations.github_workflow import (
        cron_for_kst_time,
        get_crons,
        parse_cron_to_kst,
        set_cron,
    )

    try:
        hh, mm = kst_time.split(":")
        new_cron = cron_for_kst_time(int(hh), int(mm))
    except (ValueError, AttributeError):
        click.echo(f"error: --time format은 'HH:MM' (got {kst_time!r})", err=True)
        sys.exit(1)

    path = Path(workflow_path).expanduser() if workflow_path else _resolve_workflow()
    if not path.exists():
        click.echo(f"error: workflow not found: {path}", err=True)
        sys.exit(1)

    current = get_crons(path)
    if idx >= len(current):
        click.echo(f"error: cron[{idx}] 없음 (have {len(current)})", err=True)
        sys.exit(1)
    old_cron = current[idx]
    old_kst = parse_cron_to_kst(old_cron)
    old_kst_str = f"KST {old_kst[0]:02d}:{old_kst[1]:02d}" if old_kst else "(non-daily)"
    click.echo(f"workflow : {path}")
    click.echo(f"current  : {old_cron} ({old_kst_str})")
    click.echo(f"new      : {new_cron} (KST {kst_time})")
    if not yes:
        click.confirm("적용?", abort=True)

    ok, msg = set_cron(path, new_cron, idx=idx)
    if not ok:
        click.echo(f"✗ {msg}", err=True)
        sys.exit(1)
    click.echo(f"✓ {msg}")
    click.echo("  (commit + push 후 GitHub Actions 다음 trigger부터 적용)")


def _resolve_workflow() -> Path:
    env = os.environ.get("EDITH_DS_DIGEST_WORKFLOW")
    if env:
        return Path(env).expanduser()
    raise click.UsageError("--workflow PATH 또는 EDITH_DS_DIGEST_WORKFLOW env 필요")


if __name__ == "__main__":
    main()
