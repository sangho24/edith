"""Phase 3 F2 — Calendar Collector + today view.

CalendarSource ABC + LocalCalendarSource (JSON fixture, dev/test) +
GoogleCalendarSource (placeholder, F2.x에서 OAuth 후 활성화) +
EventKitCalendarSource (PR #16, macOS Apple Calendar).

today_view(source) → 오늘 일정 list + busy minutes 합계.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    description: str | None = None
    location: str | None = None
    url: str | None = None

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    def to_summary(self) -> str:
        # UTC-aware datetime 이면 local 로 변환해서 표시 (사용자 시점 시간).
        s_dt = self.start.astimezone() if self.start.tzinfo else self.start
        e_dt = self.end.astimezone() if self.end.tzinfo else self.end
        s = s_dt.strftime("%H:%M")
        e = e_dt.strftime("%H:%M")
        return f"{s}-{e} {self.title}"


class CalendarSource(ABC):
    @abstractmethod
    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    def today(self, now: datetime | None = None) -> list[CalendarEvent]:
        if now is None:
            # 기존 호환: now 미지정이면 UTC 날짜 창 (None 경로는 건드리지 않는다).
            ref = datetime.now(UTC)
            tz = UTC
            day = ref.date()
        else:
            # now 명시: '오늘'을 Edith 시간대(기본 KST)로 통일 — UTC now가 와도 사용자 날짜.
            from harness.localtime import edith_today, edith_tz

            tz = edith_tz()
            day = edith_today(now)
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        return self.list_events(start, end)


class LocalCalendarSource(CalendarSource):
    """JSON fixture에서 events 읽기 (test/dev)."""

    def __init__(self, events_path: Path) -> None:
        self.events_path = events_path

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        if not self.events_path.exists():
            return []
        try:
            data = json.loads(self.events_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        events: list[CalendarEvent] = []
        for item in data:
            ev_start = datetime.fromisoformat(item["start"])
            ev_end = datetime.fromisoformat(item["end"])
            if start <= ev_start < end:
                events.append(
                    CalendarEvent(
                        id=item["id"],
                        title=item["title"],
                        start=ev_start,
                        end=ev_end,
                        attendees=item.get("attendees", []),
                        description=item.get("description"),
                        location=item.get("location"),
                        url=item.get("url"),
                    )
                )
        events.sort(key=lambda e: e.start)
        return events


class GoogleCalendarSource(CalendarSource):
    """Google Calendar API readonly. OAuth 필요. F2.x에서 구현."""

    def __init__(self, token_path: Path | None = None) -> None:
        self.token_path = token_path or Path.home() / ".config" / "edith" / "google_token.json"

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        if not self.token_path.exists():
            raise RuntimeError(
                f"Google OAuth 미설정 ({self.token_path} 없음). "
                f"F2.x: `harness oauth google` 명령으로 설정 예정."
            )
        raise NotImplementedError("F2.x에서 google-api-python-client 통합")


class EventKitCalendarSource(CalendarSource):
    """PR #16 — macOS EventKit 어댑터 (Apple Calendar 직읽음).

    harness.integrations.apple_calendar.EventKitCalendarSource (raw) 의 결과를
    F2 CalendarEvent 형식으로 변환. raw 는 naive local datetime → UTC-aware 로 정규화.
    """

    def __init__(self, _raw_source: Any | None = None) -> None:
        if _raw_source is not None:
            # 테스트 시 mock 주입
            self._raw = _raw_source
            return
        from harness.integrations.apple_calendar import (
            EventKitCalendarSource as _RawEventKit,
        )
        self._raw = _RawEventKit()

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        # raw 의 range 는 date 단위. day-level 로 확장.
        raw_events = self._raw.range(start.date(), end.date())
        out: list[CalendarEvent] = []
        local_tz = datetime.now().astimezone().tzinfo
        for idx, raw in enumerate(raw_events):
            # raw.start/end 는 naive local datetime → local TZ 부여 → UTC 변환
            ev_start = raw.start.replace(tzinfo=local_tz).astimezone(UTC)
            ev_end = raw.end.replace(tzinfo=local_tz).astimezone(UTC)
            if start <= ev_start < end:
                out.append(
                    CalendarEvent(
                        id=f"ek_{idx}_{int(ev_start.timestamp())}",
                        title=raw.title,
                        start=ev_start,
                        end=ev_end,
                        attendees=[],
                        description=getattr(raw, "notes", None) or None,
                        location=getattr(raw, "location", None) or None,
                        url=None,
                    )
                )
        return out


def select_source(
    edith_home: Path | None = None,
    fixture_path: Path | None = None,
) -> CalendarSource:
    """OS·환경에 따라 적절한 CalendarSource 선택.

    우선순위:
    1. fixture_path 명시 → LocalCalendarSource (테스트/시연 override)
    2. macOS + pyobjc-framework-EventKit → EventKitCalendarSource
    3. fallback → LocalCalendarSource(edith_home/raw/calendar/events.json)
    """
    import sys

    if fixture_path is not None:
        return LocalCalendarSource(fixture_path)

    if sys.platform == "darwin":
        try:
            return EventKitCalendarSource()
        except RuntimeError:
            pass

    home = edith_home or Path.home() / "edith"
    return LocalCalendarSource(home / "raw" / "calendar" / "events.json")


def today_view(source: CalendarSource, now: datetime | None = None) -> dict:
    """오늘 일정 요약 dict. now 주입 시 그 날짜·tz 기준(테스트/데모 결정성)."""
    events = source.today(now)
    return {
        "n_events": len(events),
        "events": [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start.isoformat(),
                "end": e.end.isoformat(),
                "duration_min": e.duration_minutes(),
                "attendees": e.attendees,
                "location": e.location,
                "url": e.url,
                "summary": e.to_summary(),
            }
            for e in events
        ],
        "total_busy_minutes": sum(e.duration_minutes() for e in events),
    }


def render_today(view: dict) -> str:
    """text 렌더링 — CLI 출력용."""
    lines = ["─" * 50]
    n = view["n_events"]
    if n == 0:
        lines.append("오늘 일정: 없음")
        lines.append("─" * 50)
        return "\n".join(lines)
    busy = view["total_busy_minutes"]
    lines.append(f"오늘 {n}건 · 총 {busy}분 ({busy / 60:.1f}h)")
    lines.append("─" * 50)
    for ev in view["events"]:
        line = f"  {ev['summary']}"
        if ev.get("attendees"):
            line += f" · {len(ev['attendees'])}명"
        if ev.get("location"):
            line += f" · {ev['location']}"
        lines.append(line)
    return "\n".join(lines)
