"""Phase 3 F2 — Calendar Collector + today view.

CalendarSource ABC + LocalCalendarSource (JSON fixture, dev/test) +
GoogleCalendarSource (placeholder, F2.x에서 OAuth 후 활성화).

today_view(source) → 오늘 일정 list + busy minutes 합계.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path


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
        s = self.start.strftime("%H:%M")
        e = self.end.strftime("%H:%M")
        return f"{s}-{e} {self.title}"


class CalendarSource(ABC):
    @abstractmethod
    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    def today(self) -> list[CalendarEvent]:
        now = datetime.now(UTC)
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
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


def today_view(source: CalendarSource) -> dict:
    """오늘 일정 요약 dict."""
    events = source.today()
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
