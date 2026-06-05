"""체감 데모용 시드 — '오늘' 날짜의 현실적 raw/ 샘플 생성.

선제 엔진(initiative)·morning brief가 실제 신호를 보이도록 mail/calendar/digest/
health/reading을 한 번에 깔아준다. 이렇게 깔면 `harness demo` 한 번으로 아침 brief +
선제 제안(긴급 메일·일정 충돌·digest 미정리·읽기목록 방치·수면 부족)이 실제로 뜬다.

성격: **합성 데모 데이터**다. 사용자/collector가 넣는 실데이터와 같은 위치를 쓰되,
이미 파일이 있으면 덮어쓰지 않는다(skip; --force로만 교체). raw/ 불변 원칙을 존중해
기존 데이터를 절대 건드리지 않는다.

시각은 모두 KST(+09:00)로 stamp하며, 일정·헬스 신호가 그날 창에 들어오도록
seed 날짜와 `harness demo --now`의 기준 시각(그날 08:00 KST)을 일치시킨다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class SeedFile:
    """시드 파일 한 개 — raw/ 기준 상대경로 + 내용."""

    relpath: str
    content: str


def _iso(d: date, hh: int, mm: int) -> str:
    """KST 기준 'd hh:mm' ISO 문자열."""
    return datetime.combine(d, time(hh, mm), tzinfo=KST).isoformat()


def _json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def build_mail(d: date) -> str:
    """urgent/important/newsletter/notification/normal 한 건씩 — triage 분류 시연용."""
    msgs = [
        {
            "id": "demo-mail-urgent",
            "sender": "client@acme.com",
            "subject": "긴급: 계약서 검토 — 오늘까지 회신 부탁드립니다",
            "snippet": "첨부 계약서 2건 검토 후 오늘 안에 회신 주시면 감사하겠습니다.",
            "received_at": _iso(d, 7, 12),
            "labels": [],
            "unread": True,
        },
        {
            "id": "demo-mail-important",
            "sender": "lead@company.com",
            "subject": "주간 팀 회의 일정 조율",
            "snippet": "다음 주 스프린트 리뷰 시간 투표 부탁드립니다.",
            "received_at": _iso(d, 6, 40),
            "labels": [],
            "unread": True,
        },
        {
            "id": "demo-mail-newsletter",
            "sender": "newsletter@medium.com",
            "subject": "이번 주 ML 다이제스트",
            "snippet": "주목할 만한 논문과 글 모음.",
            "received_at": _iso(d, 5, 0),
            "labels": ["Promotions"],
            "unread": True,
        },
        {
            "id": "demo-mail-notif",
            "sender": "notifications@github.com",
            "subject": "[edith] PR #42 merged",
            "snippet": "Your pull request was merged.",
            "received_at": _iso(d, 4, 30),
            "labels": [],
            "unread": True,
        },
        {
            "id": "demo-mail-normal",
            "sender": "friend@gmail.com",
            "subject": "주말에 커피 한잔?",
            "snippet": "오랜만에 얼굴 보자.",
            "received_at": _iso(d, 3, 0),
            "labels": [],
            "unread": True,
        },
    ]
    return _json(msgs)


def build_calendar(d: date) -> str:
    """오늘 일정 4건 — 10:00 회의와 10:30 콜이 시간상 겹쳐 conflict 신호 생성."""
    events = [
        {
            "id": "demo-ev-standup",
            "title": "데일리 스탠드업",
            "start": _iso(d, 9, 0),
            "end": _iso(d, 9, 15),
            "attendees": ["team@company.com"],
        },
        {
            "id": "demo-ev-roadmap",
            "title": "제품 로드맵 회의",
            "start": _iso(d, 10, 0),
            "end": _iso(d, 11, 0),
            "attendees": ["pm@company.com", "lead@company.com"],
            "location": "회의실 A",
        },
        {
            "id": "demo-ev-client",
            "title": "클라이언트 콜 — Acme",
            "start": _iso(d, 10, 30),
            "end": _iso(d, 11, 30),
            "attendees": ["client@acme.com"],
            "url": "https://meet.example.com/acme",
        },
        {
            "id": "demo-ev-mentoring",
            "title": "1:1 멘토링",
            "start": _iso(d, 14, 0),
            "end": _iso(d, 15, 0),
            "attendees": ["mentee@company.com"],
        },
    ]
    return _json(events)


def build_digest(d: date) -> str:
    """ds-digest 최신 2건 — 미정리 리마인드 신호 생성."""
    data = {
        "date": d.isoformat(),
        "items": [
            {
                "title": "Mixture-of-Experts 라우팅의 최신 동향",
                "source": "arxiv",
                "url": "https://arxiv.org/abs/2605.00001",
                "summary": "MoE 라우팅 안정화 기법 비교.",
                "score": 9.1,
            },
            {
                "title": "LLM 평가 파이프라인 베스트 프랙티스",
                "source": "hn",
                "url": "https://news.ycombinator.com/item?id=99999999",
                "summary": "골든셋·회귀·오프라인 평가 운영 노하우.",
                "score": 8.4,
            },
        ],
    }
    return _json(data)


def build_health(d: date) -> str:
    """Apple Health export.xml — 수면 300분(<6h)으로 수면 부족 nudge 신호 생성."""
    # 수면은 그날 새벽(00:30~05:30)으로 stamp → start.date()==d → daily_summary가 오늘로 집계.
    records = [
        f'<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Mi Fitness" '
        f'unit="count" startDate="{_xml_dt(d, 8, 0)}" endDate="{_xml_dt(d, 8, 10)}" '
        f'value="4210"/>',
        f'<Record type="HKQuantityTypeIdentifierActiveEnergyBurned" sourceName="Mi Fitness" '
        f'unit="kcal" startDate="{_xml_dt(d, 8, 0)}" endDate="{_xml_dt(d, 20, 0)}" '
        f'value="312"/>',
        f'<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Mi Fitness" '
        f'unit="" startDate="{_xml_dt(d, 0, 30)}" endDate="{_xml_dt(d, 5, 30)}" '
        f'value="HKCategoryValueSleepAnalysisAsleepUnspecified"/>',
    ]
    return '<?xml version="1.0"?>\n<HealthData>\n' + "\n".join(records) + "\n</HealthData>\n"


def _xml_dt(d: date, hh: int, mm: int) -> str:
    """Apple Health export.xml 의 '%Y-%m-%d %H:%M:%S %z' 형식(KST)."""
    return datetime.combine(d, time(hh, mm), tzinfo=KST).strftime("%Y-%m-%d %H:%M:%S %z")


def build_reading(d: date) -> str:
    """읽기목록 — 2건이 14일+ 방치(stale), 1건은 최근, 1건은 읽음."""
    queue = [
        {
            "title": "Chain-of-Thought의 한계: 최신 비판 논문",
            "url": "https://arxiv.org/abs/2604.10001",
            "added_at": (d - timedelta(days=25)).isoformat(),
            "read": False,
        },
        {
            "title": "RAG 서베이 2026 (꼭 정리)",
            "url": "https://arxiv.org/abs/2604.10002",
            "added_at": (d - timedelta(days=21)).isoformat(),
            "read": False,
        },
        {
            "title": "Mamba/SSM 입문 글",
            "url": "https://example.com/mamba-intro",
            "added_at": (d - timedelta(days=4)).isoformat(),
            "read": False,
        },
        {
            "title": "이미 읽고 정리한 글",
            "url": "https://example.com/done",
            "added_at": (d - timedelta(days=40)).isoformat(),
            "read": True,
        },
    ]
    return _json(queue)


def seed_files(d: date) -> list[SeedFile]:
    """그날 시드 파일 전체."""
    return [
        SeedFile("raw/mail/messages.json", build_mail(d)),
        SeedFile("raw/calendar/events.json", build_calendar(d)),
        SeedFile("raw/digest/latest.json", build_digest(d)),
        SeedFile("raw/health/export.xml", build_health(d)),
        SeedFile("raw/reading/queue.json", build_reading(d)),
    ]


def seed_demo(
    edith_home: Path, target_date: date | None = None, force: bool = False
) -> dict:
    """그날 데모 시드를 raw/ 아래에 기록.

    Args:
        edith_home: Edith 홈.
        target_date: 시드 기준 날짜(기본 오늘 KST). demo의 now 기준일과 일치해야 한다.
        force: True면 기존 파일도 덮어쓴다. False(기본)면 있으면 skip(실데이터 보호).

    Returns:
        {"date", "written": [relpath...], "skipped": [relpath...]}.
    """
    d = target_date or datetime.now(KST).date()
    written: list[str] = []
    skipped: list[str] = []
    for sf in seed_files(d):
        path = edith_home / sf.relpath
        if path.exists() and not force:
            skipped.append(sf.relpath)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sf.content, encoding="utf-8")
        written.append(sf.relpath)
    return {"date": d.isoformat(), "written": written, "skipped": skipped}


# ── 데모 제안 (Proposals/Approvals 탭 체험용) ──
#
# LLM 키 없이도 GUI에서 "제안 검토 → 부분 승인 → 실행" 전체 루프를 클릭해볼 수 있게
# 샘플 Proposal을 proposals.json에 심는다. external step 중 하나(github_workflow_update_cron)는
# 실제로 실행되어 머신 로컬 데모 워크플로우 파일의 cron을 바꾼다(가역). gmail_send step은
# OAuth 미설정 시 실행 단계에서 안전하게 차단되는 경계를 보여준다.

DEMO_WORKFLOW_RELPATH = "harness/demo_workflow.yml"  # 머신 로컬(gitignore), external 실행 대상
DEMO_PROPOSAL_TRIGGER = "demo"


def build_demo_workflow() -> str:
    """cron 한 줄이 있는 최소 GitHub Actions 워크플로우(데모 external 실행 대상)."""
    return (
        "name: demo-ds-digest\n"
        "on:\n"
        "  schedule:\n"
        "    - cron: '10 22 * * *'  # 07:10 KST\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo demo\n"
    )


def seed_demo_proposal(edith_home: Path, force: bool = False) -> dict:
    """데모 Proposal 1건 + 데모 워크플로우 파일을 심는다(멱등).

    이미 proposed 상태의 데모 제안이 있으면 새로 만들지 않는다(반복 실행해도 누적 X).
    사용자가 그 제안을 처리(accept/reject로 close)한 뒤 다시 부르면 새 제안을 만든다.

    Returns:
        {"created": bool, "proposal_id": str, ...}.
    """
    from harness.integrations.github_workflow import cron_for_kst_time
    from harness.propose import ProposalStep, ProposalStore

    wf = edith_home / DEMO_WORKFLOW_RELPATH
    if force or not wf.exists():
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(build_demo_workflow(), encoding="utf-8")

    store = ProposalStore(edith_home / "harness" / "proposals.json")
    # 제안은 force와 무관하게 멱등 — 이미 proposed 데모 제안이 있으면 중복 생성하지 않는다
    # (serve-demo 반복 실행 시 누적 방지). 사용자가 처리(close)하면 다음 호출이 새로 만든다.
    existing = [
        p for p in store.list(status="proposed") if p.trigger == DEMO_PROPOSAL_TRIGGER
    ]
    if existing:
        return {"created": False, "proposal_id": existing[0].id, "reason": "already-proposed"}

    steps = [
        ProposalStep(
            idx=0,
            intent="이번 주 ds-digest 하이라이트를 wiki로 정리",
            explanation="digest 2건을 요약해 concepts 페이지에 누적 — 내부 작업, 승인 불필요.",
            expected_outcome="wiki/concepts/ds-digest-주간.md 갱신",
            support_refs=["raw/digest/latest.json"],
            action_type="",  # internal → 승인 큐 대상 아님
            reversible=True,
            risk_score=2,
        ),
        ProposalStep(
            idx=1,
            intent="ds-digest 발송 시각 07:10 → 08:00 (KST)로 변경",
            explanation="아침 brief 시점과 맞춰 digest 미정리 누적을 줄임.",
            expected_outcome="워크플로우 cron 변경(파일 수정; commit·push는 별도).",
            risk_note="가역 — 언제든 되돌릴 수 있음.",
            support_refs=[DEMO_WORKFLOW_RELPATH],
            action_type="github_workflow_update_cron",
            params={
                "workflow_path": DEMO_WORKFLOW_RELPATH,
                "new_cron": cron_for_kst_time(8, 0),
            },
            reversible=True,
            risk_score=4,
        ),
        ProposalStep(
            idx=2,
            intent="digest 요약을 본인 메일로 발송",
            explanation="외부 발송 — 승인 + Gmail OAuth 필요. 미설정이면 실행 단계에서 안전 차단.",
            expected_outcome="요약 메일 1통.",
            risk_note="비가역(발송). OAuth 없으면 실행되지 않음.",
            support_refs=["raw/digest/latest.json"],
            action_type="gmail_send",
            params={
                "to": "demo@example.com",
                "subject": "[데모] ds-digest 요약",
                "body": "데모 본문 — 실제 발송은 OAuth 설정 후.",
            },
            reversible=False,
            risk_score=6,
        ),
    ]
    p = store.create(
        title="ds-digest 운영 개선 (발송시각 조정 + 요약 메일)",
        rationale="오늘 digest 2건 도착 + 아침 brief와 시점 불일치 — 운영 흐름 정리 제안.",
        scope="personal",
        steps=steps,
        trigger=DEMO_PROPOSAL_TRIGGER,
    )
    return {"created": True, "proposal_id": p.id, "workflow": DEMO_WORKFLOW_RELPATH}


__all__ = [
    "DEMO_WORKFLOW_RELPATH",
    "KST",
    "SeedFile",
    "build_calendar",
    "build_demo_workflow",
    "build_digest",
    "build_health",
    "build_mail",
    "build_reading",
    "seed_demo",
    "seed_demo_proposal",
    "seed_files",
]
