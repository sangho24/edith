"""Phase 3 F2 — Calendar tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest

from harness.calendar import (
    CalendarEvent,
    GoogleCalendarSource,
    LocalCalendarSource,
    render_today,
    today_view,
)


def _make_events_file(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")


def _today_iso(hour: int, minute: int = 0) -> str:
    today = datetime.now(UTC).date()
    return datetime.combine(today, time(hour, minute), tzinfo=UTC).isoformat()


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    return tmp_path / "events.json"


def test_local_source_empty_when_no_file(events_file: Path) -> None:
    src = LocalCalendarSource(events_file)
    assert src.today() == []


def test_local_source_filters_to_today(events_file: Path) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).replace(hour=10, minute=0)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).replace(hour=10, minute=0)
    _make_events_file(
        events_file,
        [
            {
                "id": "e1",
                "title": "어제 회의",
                "start": yesterday.isoformat(),
                "end": (yesterday + timedelta(hours=1)).isoformat(),
                "attendees": [],
            },
            {
                "id": "e2",
                "title": "오늘 회의",
                "start": _today_iso(10),
                "end": _today_iso(11),
                "attendees": ["a@b.com"],
            },
            {
                "id": "e3",
                "title": "내일 회의",
                "start": tomorrow.isoformat(),
                "end": (tomorrow + timedelta(hours=1)).isoformat(),
                "attendees": [],
            },
        ],
    )
    src = LocalCalendarSource(events_file)
    events = src.today()
    assert len(events) == 1
    assert events[0].title == "오늘 회의"


def test_today_view_aggregates(events_file: Path) -> None:
    _make_events_file(
        events_file,
        [
            {
                "id": "e1",
                "title": "회의 A",
                "start": _today_iso(10),
                "end": _today_iso(11),
                "attendees": ["x@y.com", "z@y.com"],
            },
            {
                "id": "e2",
                "title": "회의 B",
                "start": _today_iso(14),
                "end": _today_iso(15, 30),
                "attendees": [],
            },
        ],
    )
    view = today_view(LocalCalendarSource(events_file))
    assert view["n_events"] == 2
    assert view["total_busy_minutes"] == 60 + 90
    assert view["events"][0]["title"] == "회의 A"
    assert view["events"][1]["title"] == "회의 B"


def test_today_view_sorted_by_start(events_file: Path) -> None:
    _make_events_file(
        events_file,
        [
            {
                "id": "later",
                "title": "오후",
                "start": _today_iso(15),
                "end": _today_iso(16),
                "attendees": [],
            },
            {
                "id": "earlier",
                "title": "오전",
                "start": _today_iso(9),
                "end": _today_iso(10),
                "attendees": [],
            },
        ],
    )
    events = LocalCalendarSource(events_file).today()
    assert events[0].title == "오전"
    assert events[1].title == "오후"


def test_render_today_empty() -> None:
    text = render_today({"n_events": 0, "events": [], "total_busy_minutes": 0})
    assert "없음" in text


def test_render_today_with_events(events_file: Path) -> None:
    _make_events_file(
        events_file,
        [
            {
                "id": "e1",
                "title": "Edith retro",
                "start": _today_iso(10),
                "end": _today_iso(11),
                "attendees": ["sam@a.com"],
                "location": "Zoom",
            }
        ],
    )
    view = today_view(LocalCalendarSource(events_file))
    text = render_today(view)
    assert "1건" in text
    assert "Edith retro" in text
    assert "1명" in text
    assert "Zoom" in text


def test_calendar_event_duration() -> None:
    ev = CalendarEvent(
        id="x",
        title="t",
        start=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        end=datetime(2026, 4, 28, 11, 30, tzinfo=UTC),
        attendees=[],
    )
    assert ev.duration_minutes() == 90
    assert "10:00-11:30 t" == ev.to_summary()


def test_local_source_handles_corrupt_json(events_file: Path) -> None:
    events_file.write_text("{broken", encoding="utf-8")
    src = LocalCalendarSource(events_file)
    assert src.today() == []


def test_google_source_raises_when_unconfigured(tmp_path: Path) -> None:
    src = GoogleCalendarSource(token_path=tmp_path / "missing.json")
    with pytest.raises(RuntimeError) as exc:
        src.today()
    assert "OAuth" in str(exc.value)
