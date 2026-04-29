"""PR #14 — Apple Calendar tests (platform-agnostic).

EventKitCalendarSource 자체는 macOS + pyobjc 필요해서 sandbox 에선 skip.
Mock + 추상화 + helper 함수만 검증.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

import pytest

from harness.integrations.apple_calendar import (
    CalendarEvent,
    EventKitCalendarSource,
    MockCalendarSource,
    format_for_brief,
    get_calendar_source,
    split_by_part_of_day,
)

# ── CalendarEvent ───────────────────────────────────────────────────────


def test_event_duration_minutes() -> None:
    e = CalendarEvent(
        title="회의",
        start=datetime(2026, 4, 29, 10, 0),
        end=datetime(2026, 4, 29, 11, 30),
    )
    assert e.duration_minutes() == 90


def test_event_time_label_normal() -> None:
    e = CalendarEvent(
        title="x",
        start=datetime(2026, 4, 29, 9, 0),
        end=datetime(2026, 4, 29, 10, 0),
    )
    assert e.time_label() == "09:00-10:00"


def test_event_time_label_all_day() -> None:
    e = CalendarEvent(
        title="x",
        start=datetime(2026, 4, 29, 0, 0),
        end=datetime(2026, 4, 29, 23, 59),
        all_day=True,
    )
    assert e.time_label() == "하루 종일"


# ── MockCalendarSource ──────────────────────────────────────────────────


def test_mock_today_filters_by_date() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_9 = datetime.combine(today, datetime.min.time()).replace(hour=9)
    today_10 = datetime.combine(today, datetime.min.time()).replace(hour=10)
    yest_9 = datetime.combine(yesterday, datetime.min.time()).replace(hour=9)
    yest_10 = datetime.combine(yesterday, datetime.min.time()).replace(hour=10)
    src = MockCalendarSource(
        [
            CalendarEvent("today_a", today_9, today_10),
            CalendarEvent("yesterday", yest_9, yest_10),
        ]
    )
    today_events = src.today()
    assert len(today_events) == 1
    assert today_events[0].title == "today_a"


def test_mock_range() -> None:
    base = date(2026, 4, 29)
    src = MockCalendarSource(
        [
            CalendarEvent("a", datetime(2026, 4, 29, 9, 0), datetime(2026, 4, 29, 10, 0)),
            CalendarEvent("b", datetime(2026, 4, 30, 9, 0), datetime(2026, 4, 30, 10, 0)),
            CalendarEvent("c", datetime(2026, 5, 1, 9, 0), datetime(2026, 5, 1, 10, 0)),
        ]
    )
    out = src.range(base, base + timedelta(days=1))
    titles = {e.title for e in out}
    assert titles == {"a", "b"}


def test_mock_empty() -> None:
    src = MockCalendarSource()
    assert src.today() == []
    assert src.range(date.today(), date.today()) == []


# ── format_for_brief ────────────────────────────────────────────────────


def test_format_for_brief_empty() -> None:
    assert format_for_brief([]) == "오늘 일정 없음"


def test_format_for_brief_sorted() -> None:
    events = [
        CalendarEvent(
            "1on1",
            datetime(2026, 4, 29, 14, 30),
            datetime(2026, 4, 29, 15, 0),
            calendar_name="personal",
        ),
        CalendarEvent(
            "디자인 리뷰",
            datetime(2026, 4, 29, 9, 0),
            datetime(2026, 4, 29, 10, 0),
            calendar_name="work",
        ),
    ]
    out = format_for_brief(events)
    # 시간순 — 09:00 이 먼저
    assert out.index("디자인 리뷰") < out.index("1on1")
    assert "(work)" in out
    assert "(personal)" in out


def test_format_for_brief_no_calendar_name() -> None:
    events = [
        CalendarEvent("x", datetime(2026, 4, 29, 9, 0), datetime(2026, 4, 29, 10, 0))
    ]
    out = format_for_brief(events)
    assert out == "09:00-10:00 x"


# ── split_by_part_of_day ────────────────────────────────────────────────


def test_split_by_part_of_day() -> None:
    events = [
        CalendarEvent("아침", datetime(2026, 4, 29, 8, 0), datetime(2026, 4, 29, 9, 0)),
        CalendarEvent("오전", datetime(2026, 4, 29, 11, 0), datetime(2026, 4, 29, 12, 0)),
        CalendarEvent("오후", datetime(2026, 4, 29, 14, 0), datetime(2026, 4, 29, 15, 0)),
        CalendarEvent("저녁", datetime(2026, 4, 29, 19, 0), datetime(2026, 4, 29, 20, 0)),
        CalendarEvent(
            "종일",
            datetime(2026, 4, 29, 0, 0),
            datetime(2026, 4, 29, 23, 59),
            all_day=True,
        ),
    ]
    parts = split_by_part_of_day(events)
    assert {e.title for e in parts["morning"]} == {"아침", "오전", "종일"}
    assert {e.title for e in parts["afternoon"]} == {"오후"}
    assert {e.title for e in parts["evening"]} == {"저녁"}


# ── get_calendar_source ─────────────────────────────────────────────────


def test_get_source_fallback_to_mock_on_non_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux 등에선 Mock fallback."""
    monkeypatch.setattr(sys, "platform", "linux")
    src = get_calendar_source(fallback_to_mock=True)
    assert isinstance(src, MockCalendarSource)


def test_get_source_raise_on_non_macos_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError):
        get_calendar_source(fallback_to_mock=False)


# ── EventKitCalendarSource (macOS only) ─────────────────────────────────


@pytest.mark.skipif(sys.platform != "darwin", reason="EventKit 은 macOS 전용")
def test_eventkit_init_requires_macos() -> None:
    """macOS 에서 import + init 이 raise 안 함만 검증 (실 캘린더 read 는 e2e 환경)."""
    try:
        EventKitCalendarSource()
    except RuntimeError as e:
        # pyobjc-framework-EventKit 미설치 — sandbox 가 macOS 시뮬레이션 시도하면 발생 가능
        assert "pyobjc" in str(e).lower() or "macOS" in str(e)


def test_eventkit_init_raises_on_non_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        EventKitCalendarSource()
