"""PR #14 — Apple Calendar via EventKit (macOS only).

EventKit 은 macOS 시스템 프레임워크. pyobjc-framework-EventKit 으로 접근.
이 파일은 platform-agnostic 추상화 + EventKit 구현 + Mock 구현.

Sandbox / 비-macOS 환경에선 자동으로 Mock 사용 (lazy import).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Protocol


@dataclass(frozen=True)
class CalendarEvent:
    """캘린더 이벤트의 platform-agnostic 표현."""

    title: str
    start: datetime
    end: datetime
    location: str = ""
    notes: str = ""
    calendar_name: str = ""
    all_day: bool = False

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    def time_label(self) -> str:
        """morning brief 용 — '09:00-10:30' 또는 '하루 종일'."""
        if self.all_day:
            return "하루 종일"
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')}"


class CalendarSource(Protocol):
    """캘린더 source interface — platform-agnostic.

    구현체:
    - EventKitCalendarSource (macOS 실 환경)
    - MockCalendarSource (테스트)
    - 추후: ICloudCalDAVSource (Windows/Linux 운영 시)
    """

    def today(self) -> list[CalendarEvent]: ...

    def range(self, start_date: date, end_date: date) -> list[CalendarEvent]: ...


class MockCalendarSource:
    """테스트용 — 미리 정한 이벤트 리스트 반환."""

    def __init__(self, events: list[CalendarEvent] | None = None) -> None:
        self._events = events or []

    def today(self) -> list[CalendarEvent]:
        today_d = date.today()
        return [e for e in self._events if e.start.date() == today_d]

    def range(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        return [
            e
            for e in self._events
            if start_date <= e.start.date() <= end_date
        ]


def _is_macos() -> bool:
    return sys.platform == "darwin"


class EventKitCalendarSource:
    """macOS EventKit 기반 — Calendar.app 이 보는 모든 캘린더 직읽음.

    iCloud + 구독 + 로컬 다 포함. 인증 거의 없음 (첫 실행 시 macOS 가 한 번 동의 다이얼로그).
    """

    def __init__(self) -> None:
        if not _is_macos():
            raise RuntimeError(
                "EventKitCalendarSource 는 macOS 전용. 다른 OS 면 ICloudCalDAVSource 사용."
            )
        try:
            # pyobjc 의 EventKit 은 동적 framework 모듈 — 정적 분석기는 심볼 못 봄.
            from EventKit import (  # pyright: ignore[reportAttributeAccessIssue,reportMissingImports] # noqa: I001
                EKEntityTypeEvent,
                EKEventStore,
            )
        except ImportError as e:
            raise RuntimeError(
                "pyobjc-framework-EventKit 필요. uv pip install pyobjc-framework-EventKit"
            ) from e

        self._EKEntityTypeEvent = EKEntityTypeEvent
        self.store = EKEventStore.alloc().init()
        # 권한 요청 — 첫 호출 시 macOS 다이얼로그 (허용 후 영구 저장)
        self._ensure_access()

    def _ensure_access(self) -> None:
        # macOS 14+ 에서는 requestFullAccessToEventsWithCompletion 사용 권장.
        # 13 이하는 requestAccessToEntityType.
        # 일단 단순 호출 (return value 없이 호출 — 동기적 결과 보장 X 지만 첫 시도엔 충분).
        try:
            self.store.requestFullAccessToEventsWithCompletion_(  # type: ignore[attr-defined]
                lambda granted, err: None
            )
        except (AttributeError, TypeError):
            try:
                self.store.requestAccessToEntityType_completion_(  # type: ignore[attr-defined]
                    self._EKEntityTypeEvent, lambda granted, err: None
                )
            except Exception:
                pass

    def today(self) -> list[CalendarEvent]:
        today_d = date.today()
        return self.range(today_d, today_d)

    def range(self, start_date: date, end_date: date) -> list[CalendarEvent]:
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)
        cals = self.store.calendarsForEntityType_(self._EKEntityTypeEvent)
        predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
            start_dt, end_dt, cals
        )
        ek_events = self.store.eventsMatchingPredicate_(predicate) or []
        return [self._convert(e) for e in ek_events]

    def _convert(self, ek_event: Any) -> CalendarEvent:
        return CalendarEvent(
            title=str(ek_event.title() or ""),
            start=_nsdate_to_datetime(ek_event.startDate()),
            end=_nsdate_to_datetime(ek_event.endDate()),
            location=str(ek_event.location() or ""),
            notes=str(ek_event.notes() or ""),
            calendar_name=str(ek_event.calendar().title() or "") if ek_event.calendar() else "",
            all_day=bool(ek_event.isAllDay()),
        )


def _nsdate_to_datetime(nsdate: Any) -> datetime:
    """NSDate → datetime. timeIntervalSince1970 은 float."""
    if nsdate is None:
        return datetime.min
    try:
        ts = nsdate.timeIntervalSince1970()
        return datetime.fromtimestamp(ts)
    except AttributeError:
        # 이미 datetime 이거나 다른 타입
        if isinstance(nsdate, datetime):
            return nsdate
        return datetime.min


def get_calendar_source(
    fallback_to_mock: bool = True,
) -> CalendarSource:
    """현재 OS 에 맞는 source 반환.

    - macOS → EventKitCalendarSource
    - 그 외 → MockCalendarSource (fallback_to_mock=True) 또는 raise
    """
    if _is_macos():
        try:
            return EventKitCalendarSource()
        except RuntimeError:
            if fallback_to_mock:
                return MockCalendarSource()
            raise
    if fallback_to_mock:
        return MockCalendarSource()
    raise RuntimeError("macOS 가 아니고 fallback_to_mock=False — calendar source 없음")


def format_for_brief(events: list[CalendarEvent]) -> str:
    """morning brief 용 한 줄 요약.

    "09:00-10:00 디자인 리뷰 (work) · 14:30-15:00 1on1 (personal)"
    """
    if not events:
        return "오늘 일정 없음"
    parts = []
    for e in sorted(events, key=lambda x: x.start):
        scope_tag = f" ({e.calendar_name})" if e.calendar_name else ""
        parts.append(f"{e.time_label()} {e.title}{scope_tag}")
    return " · ".join(parts)


def split_by_part_of_day(events: list[CalendarEvent]) -> dict[str, list[CalendarEvent]]:
    """오전 / 오후 / 저녁 분류 — brief 의 "Top 3" 용."""
    morning, afternoon, evening = [], [], []
    for e in events:
        if e.all_day:
            morning.append(e)
            continue
        h = e.start.hour
        if h < 12:
            morning.append(e)
        elif h < 18:
            afternoon.append(e)
        else:
            evening.append(e)
    return {"morning": morning, "afternoon": afternoon, "evening": evening}


# ── 미래의 ICloudCalDAVSource (Windows·Linux 운영 시) ────────────────────
# class ICloudCalDAVSource:
#     """app-specific password + caldav 라이브러리. PR #14.5 에서 구현."""


__all__ = [
    "CalendarEvent",
    "CalendarSource",
    "EventKitCalendarSource",
    "MockCalendarSource",
    "get_calendar_source",
    "format_for_brief",
    "split_by_part_of_day",
]
