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


__all__ = [
    "KST",
    "SeedFile",
    "build_calendar",
    "build_digest",
    "build_health",
    "build_mail",
    "build_reading",
    "seed_demo",
    "seed_files",
]
