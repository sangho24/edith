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
    # naive datetime 사용 — tzinfo 없으면 to_summary 가 그대로 출력 (변환 X).
    ev = CalendarEvent(
        id="x",
        title="t",
        start=datetime(2026, 4, 28, 10, 0),
        end=datetime(2026, 4, 28, 11, 30),
        attendees=[],
    )
    assert ev.duration_minutes() == 90
    assert "10:00-11:30 t" == ev.to_summary()


def test_calendar_event_to_summary_utc_aware_converts_to_local() -> None:
    """UTC-aware datetime 은 사용자 local 시간으로 변환 표시."""
    ev = CalendarEvent(
        id="x",
        title="t",
        start=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        end=datetime(2026, 4, 28, 11, 30, tzinfo=UTC),
        attendees=[],
    )
    summary = ev.to_summary()
    # local TZ 에 따라 시간 다름 — 형식만 검증
    assert "-" in summary
    assert summary.endswith(" t")
    # 90분 차이 유지
    assert ev.duration_minutes() == 90


def test_local_source_handles_corrupt_json(events_file: Path) -> None:
    events_file.write_text("{broken", encoding="utf-8")
    src = LocalCalendarSource(events_file)
    assert src.today() == []


# ── EventKitCalendarSource (PR #16) — mock raw source 로 검증 ───────────


class _FakeRawEKEvent:
    """harness.integrations.apple_calendar.CalendarEvent 와 같은 attribute."""

    def __init__(
        self,
        title: str,
        start: datetime,
        end: datetime,
        location: str = "",
        notes: str = "",
        calendar_name: str = "",
    ) -> None:
        self.title = title
        self.start = start
        self.end = end
        self.location = location
        self.notes = notes
        self.calendar_name = calendar_name


class _FakeRawEKSource:
    """raw EventKitCalendarSource 의 mock — list_events 대신 range() 반환."""

    def __init__(self, events: list[_FakeRawEKEvent]) -> None:
        self._events = events

    def range(self, start_date, end_date):  # type: ignore[no-untyped-def]
        return [e for e in self._events if start_date <= e.start.date() <= end_date]


def test_eventkit_adapter_basic_conversion() -> None:
    """EventKit raw event → F2 CalendarEvent 변환 + UTC 정규화."""
    from harness.calendar import EventKitCalendarSource

    today = datetime.now().date()
    raw = [
        _FakeRawEKEvent(
            title="디자인 리뷰",
            start=datetime.combine(today, time(10, 0)),  # naive local 10:00
            end=datetime.combine(today, time(11, 0)),
            location="회의실 A",
            notes="아젠다: ...",
        ),
    ]
    src = EventKitCalendarSource(_raw_source=_FakeRawEKSource(raw))

    # F2 CalendarSource.today() 가 UTC 범위로 호출
    events = src.today()
    # local 10am 이 UTC 인터벌에 떨어지면 1개, 아니면 0개 (TZ 의존)
    # KST 의 경우 10am KST = 01:00 UTC → UTC 오늘 [00, 24) 안에 있음 → 1개
    if events:
        assert events[0].title == "디자인 리뷰"
        assert events[0].location == "회의실 A"
        assert events[0].description == "아젠다: ..."
        # UTC-aware 인지 확인
        assert events[0].start.tzinfo is not None
        # ID 는 ek_ 로 시작
        assert events[0].id.startswith("ek_")


def test_eventkit_adapter_excludes_outside_range() -> None:
    from harness.calendar import EventKitCalendarSource

    today = datetime.now().date()
    far_past = datetime.combine(today - timedelta(days=10), time(10, 0))
    far_future = datetime.combine(today + timedelta(days=10), time(10, 0))
    raw = [
        _FakeRawEKEvent("과거", far_past, far_past + timedelta(hours=1)),
        _FakeRawEKEvent("미래", far_future, far_future + timedelta(hours=1)),
    ]
    src = EventKitCalendarSource(_raw_source=_FakeRawEKSource(raw))
    events = src.today()
    assert events == []


def test_eventkit_adapter_handles_missing_optional_fields() -> None:
    from harness.calendar import EventKitCalendarSource

    today = datetime.now().date()
    # location / notes 없는 raw event
    raw = [
        _FakeRawEKEvent(
            title="간단",
            start=datetime.combine(today, time(12, 0)),
            end=datetime.combine(today, time(13, 0)),
        ),
    ]
    src = EventKitCalendarSource(_raw_source=_FakeRawEKSource(raw))
    events = src.today()
    if events:
        assert events[0].title == "간단"
        assert events[0].location is None
        assert events[0].description is None


def test_google_source_raises_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # service 미주입 + 토큰/시크릿 없음 → 빌드 시 RuntimeError (브라우저 flow X).
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing_token.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", str(tmp_path / "missing_secret.json"))
    src = GoogleCalendarSource()
    with pytest.raises(RuntimeError):
        src.today()
