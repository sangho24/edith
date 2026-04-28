"""calendar_today tool — F2 LLM 통합.

LLM이 "오늘 일정?" task를 받으면 이 tool 호출.
EDITH_CALENDAR_FIXTURE 환경변수 또는 raw/calendar/events.json 에서 읽기.
F2.x에서 GoogleCalendarSource 우선 사용으로 전환.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.calendar import LocalCalendarSource, today_view
from harness.state import Context
from harness.tools import Tool


def _calendar_today(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    fixture_path_env = os.environ.get("EDITH_CALENDAR_FIXTURE")
    fixture_path = (
        Path(fixture_path_env)
        if fixture_path_env
        else ctx.edith_home / "raw" / "calendar" / "events.json"
    )
    source = LocalCalendarSource(fixture_path)
    return today_view(source)


CALENDAR_TODAY = Tool(
    name="calendar_today",
    description="오늘 캘린더 일정 list + 총 busy minutes. read-only.",
    input_schema={"type": "object", "properties": {}},
    fn=_calendar_today,
)
