"""calendar_today tool — F2 LLM 통합.

Source 선택 우선순위:
1. EDITH_CALENDAR_FIXTURE env 설정 시 → LocalCalendarSource (test/dev override)
2. macOS + pyobjc-framework-EventKit 설치 → EventKitCalendarSource (PR #16)
3. fallback → LocalCalendarSource (raw/calendar/events.json)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from harness.calendar import (
    EventKitCalendarSource,
    LocalCalendarSource,
    today_view,
)
from harness.state import Context
from harness.tools import Tool


def _calendar_today(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    fixture_path_env = os.environ.get("EDITH_CALENDAR_FIXTURE")
    if fixture_path_env:
        # 명시적 fixture 우선 (테스트 환경 / 시연용 데이터)
        source = LocalCalendarSource(Path(fixture_path_env))
        return today_view(source)

    if sys.platform == "darwin":
        # macOS — Apple Calendar (EventKit) 우선 시도
        try:
            ek_source = EventKitCalendarSource()
            return today_view(ek_source)
        except RuntimeError:
            # pyobjc 미설치 또는 권한 거부 → fallback
            pass

    # 기본 fallback: raw/calendar/events.json
    fallback = LocalCalendarSource(ctx.edith_home / "raw" / "calendar" / "events.json")
    return today_view(fallback)


CALENDAR_TODAY = Tool(
    name="calendar_today",
    description="오늘 캘린더 일정 list + 총 busy minutes. macOS면 Apple Calendar 직읽음.",
    input_schema={"type": "object", "properties": {}},
    fn=_calendar_today,
)
