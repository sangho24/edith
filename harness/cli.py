"""CLI: harness run / harness traces / harness eval."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast

import click

# .env 자동 로드 — `source .env` 안 해도 EDITH_LLM, XAI_API_KEY 등 사용.
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass

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
    """오늘 캘린더 일정 (F2). macOS면 Apple Calendar 직읽음."""
    from harness.calendar import render_today, select_source, today_view

    home = _edith_home()
    source = select_source(
        edith_home=home,
        fixture_path=Path(fixture) if fixture else None,
    )
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
    from harness.localtime import edith_now
    from harness.morning import compose_brief

    home = _edith_home()
    b = compose_brief(home, now=edith_now())
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
    """approve + execute. status: pending → approved → executed (F17)."""
    from harness.approval import ApprovalQueue
    from harness.executor import ApprovalExecutor

    home = _edith_home()
    queue = ApprovalQueue(home / "harness" / "approvals.json")
    try:
        r = queue.approve(id_)
    except (KeyError, ValueError) as e:
        click.echo(f"✗ {e}", err=True)
        sys.exit(1)
    click.echo(f"✓ approved {r.id} ({r.action_type})")

    result = ApprovalExecutor(queue, home).execute(id_)
    if result.ok:
        click.echo(f"✓ executed — {result.detail}")
    else:
        click.echo(f"✗ execution failed — {result.error}", err=True)
        sys.exit(1)


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
@click.argument("diff_path", type=click.Path(exists=True))
@click.option("--title", default=None)
def review_pr(diff_path: str, title: str | None) -> None:
    """PR review (F7) — heuristic 1차 리뷰."""
    from harness.integrations.github_pr import LocalPRSource, review

    src = LocalPRSource(Path(diff_path), title_str=title or Path(diff_path).stem)
    r = review(src)
    click.echo(r.render_text())


@main.command()
@click.argument("jd_file", type=click.Path(exists=True))
def jd(jd_file: str) -> None:
    """JD analyzer (F9) — JD 파일 vs raw/career/resume.md."""
    from harness.integrations.jd import analyze_jd, load_resume

    home = _edith_home()
    resume = load_resume(home)
    if resume is None:
        click.echo(
            "error: raw/career/resume.md 없음. 이력서를 markdown 으로 작성해두세요.", err=True
        )
        sys.exit(1)
    jd_text = Path(jd_file).read_text(encoding="utf-8")
    analysis = analyze_jd(jd_text, resume)
    click.echo(analysis.render_text())


@main.command()
@click.option("--days", default=7, type=int)
def weekly(days: int) -> None:
    """Weekly synthesis (F10) — 지난 N일 trace + compile + wiki 합성."""
    from harness.weekly import compose_weekly

    home = _edith_home()
    syn = compose_weekly(home, days=days)
    click.echo(syn.render_text())


@main.command()
@click.option("--now", default=None, help="평가 기준 시각 ISO (테스트/디버그용)")
@click.option("--tick-seconds", default=600, type=int, help="tick 간격(초)")
def tick(now: str | None, tick_seconds: int) -> None:
    """F19 스케줄러 tick — 트리거 평가 + 선제 체크인 push (cron이 매 N분 호출).

    TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 있으면 그 채널로 push, 없으면 stdout만.
    """
    import os

    from harness.scheduler import run_tick

    home = _edith_home()
    channel = None
    recipient = None
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id.isdigit():
        from harness.integrations.channel import TelegramChannel
        from harness.integrations.telegram import TelegramClient

        channel = TelegramChannel(TelegramClient(token=token, allowed_chat_ids={int(chat_id)}))
        recipient = chat_id

    result = run_tick(home, now_iso=now, channel=channel, recipient=recipient,
                      tick_seconds=tick_seconds)
    if result["fired"]:
        click.echo(f"fired: {', '.join(result['fired'])}")
    for text in result["pushed"]:
        click.echo(f"push → {text}")
    if not result["fired"]:
        click.echo("(no trigger fired this tick)")


@main.group("oauth")
def oauth_group() -> None:
    """외부 서비스 OAuth 설정."""


@oauth_group.command("google")
@click.option("--status", is_flag=True, help="토큰/시크릿 상태만 출력 (flow 실행 안 함)")
def oauth_google(status: bool) -> None:
    """Gmail+Calendar 통합 OAuth 동의 flow(브라우저) → 토큰 저장.

    사전: Google Cloud Console에서 OAuth 클라이언트(데스크톱 앱) 만들어 받은 JSON을
    secrets/google_oauth.json (또는 GOOGLE_OAUTH_CLIENT_SECRETS_FILE)에 둔다.
    동의 후 EDITH_MAIL_BACKEND=gmail / EDITH_CALENDAR_BACKEND=google 로 실연동.
    """
    from harness.integrations.google_auth import run_oauth_flow, token_status

    if status:
        st = token_status()
        click.echo(f"token  : {st['token_file']} ({'있음' if st['token_exists'] else '없음'})")
        click.echo(f"secret : {st['secrets_file']} ({'있음' if st['secrets_exists'] else '없음'})")
        for s in st["scopes"]:
            click.echo(f"  scope: {s}")
        if not st["secrets_exists"]:
            click.echo("→ 먼저 client secret JSON을 secrets/google_oauth.json 에 두세요.")
        return

    try:
        res = run_oauth_flow()
    except RuntimeError as e:
        click.echo(f"✗ {e}", err=True)
        sys.exit(1)
    click.echo(f"✓ 토큰 저장: {res['token_file']}")
    click.echo("  scopes: " + ", ".join(res["scopes"]))
    click.echo("  실연동: EDITH_MAIL_BACKEND=gmail EDITH_CALENDAR_BACKEND=google make brief")


@main.command("seed-demo")
@click.option("--force", is_flag=True, help="기존 파일도 덮어쓰기")
@click.option("--date", "date_str", default=None, help="시드 기준일 YYYY-MM-DD (기본 오늘 KST)")
def seed_demo_cmd(force: bool, date_str: str | None) -> None:
    """체감 데모용 raw/ 샘플 시드 (mail·calendar·digest·health·reading)."""
    from datetime import date as _date

    from harness.seed_demo import seed_demo, seed_demo_proposal

    home = _edith_home()
    target = _date.fromisoformat(date_str) if date_str else None
    result = seed_demo(home, target_date=target, force=force)
    click.echo(f"seed date: {result['date']}")
    for r in result["written"]:
        click.echo(f"  + {r}")
    for r in result["skipped"]:
        click.echo(f"  · skip (이미 있음): {r}")
    if result["skipped"] and not force:
        click.echo("  (덮어쓰려면 --force)")
    prop = seed_demo_proposal(home, force=force)
    if prop["created"]:
        click.echo(f"  + 데모 제안 1건 (id={prop['proposal_id']}) → GUI Proposals 탭")
    else:
        click.echo(f"  · 데모 제안 이미 있음 (id={prop['proposal_id']})")
    click.echo("\n다음:")
    click.echo("  harness demo       # CLI 한 화면 시연 (brief + 선제 제안)")
    click.echo("  make serve-demo    # GUI 확인 → http://127.0.0.1:8765")


@main.command()
@click.option("--now", "now_iso_opt", default=None, help="기준 시각 ISO (기본 오늘 08:00 KST)")
@click.option("--no-seed", is_flag=True, help="시드 생략 (이미 깔려 있을 때)")
@click.option("--fresh", is_flag=True, help="기존 시드를 기준일로 강제 갱신 (날짜 드리프트 방지)")
def demo(now_iso_opt: str | None, no_seed: bool, fresh: bool) -> None:
    """체감 데모 — 시드 → 아침 brief → 선제 체크인 미리보기를 한 화면에.

    첫 실행은 raw/ 시드를 생성하고(이미 있으면 보존), 이후엔 preview_checkin이
    push_ledger를 소모하지 않으므로 몇 번을 돌려도 동일하게 보인다.
    """
    from datetime import datetime, time

    from harness.initiative import preview_checkin
    from harness.morning import compose_brief
    from harness.seed_demo import KST, seed_demo, seed_demo_proposal

    home = _edith_home()
    if now_iso_opt:
        ref = datetime.fromisoformat(now_iso_opt)
    else:
        ref = datetime.combine(datetime.now(KST).date(), time(8, 0), tzinfo=KST)
    now_iso = ref.isoformat()

    if not no_seed:
        res = seed_demo(home, target_date=ref.date(), force=fresh)
        if res["written"]:
            act = "갱신" if fresh else "생성"
            click.echo(f"✓ 시드 {act} ({res['date']}): {', '.join(res['written'])}")
        else:
            click.echo(f"· 시드 이미 존재 ({res['date']}) — 보존 (--fresh로 오늘 갱신)")
        prop = seed_demo_proposal(home, force=fresh)
        verb = "생성" if prop["created"] else "존재"
        click.echo(f"· 데모 제안 {verb} (id={prop['proposal_id']}) → GUI Proposals 탭")

    # 데모는 seed 일정을 읽어야 하므로 EventKit/실데이터 override env 정리 후 fixture 지정.
    for k in (
        "EDITH_DS_DIGEST_URL",
        "EDITH_DS_DIGEST_LATEST",
        "EDITH_HEALTH_EXPORT",
        "EDITH_MAIL_FIXTURE",
    ):
        os.environ.pop(k, None)
    os.environ["EDITH_CALENDAR_FIXTURE"] = str(home / "raw" / "calendar" / "events.json")

    brief = compose_brief(home, now=ref)
    click.echo("\n" + brief.render_text())

    pv = preview_checkin(home, "morning", now_iso=now_iso)
    click.echo("\n" + "─" * 50)
    click.echo(
        f"🔔 선제 체크인 (morning) — 후보 {pv['candidates_n']}건 · 오늘 cap {pv['cap']}건"
    )
    click.echo("─" * 50)
    would = set(pv["would_push"])
    for s in pv["ranked"]:
        mark = "→" if s["id"] in would else "·"
        hint = f"  [{s['action_hint']}]" if s.get("action_hint") else "  [nudge]"
        click.echo(f" {mark} {s['title']}{hint}")
        click.echo(f"     {s['why']}")
    if pv["candidates_n"] == 0:
        click.echo(" (후보 없음 — `harness seed-demo`로 시드를 먼저 깔아주세요)")
    click.echo("")
    click.echo("미리보기입니다 — 실제 push/budget 소비 없음. '→'가 오늘 실제 push 대상.")
    click.echo("GUI 조작: make serve-demo → http://127.0.0.1:8765 (Brief/Proposals/Approvals)")


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
