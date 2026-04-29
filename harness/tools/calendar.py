"""calendar_today tool — F2 LLM 통합.

source 선택은 harness.calendar.select_source 헬퍼에 위임 (CLI/Tool 통일).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.calendar import select_source, today_view
from harness.state import Context
from harness.tools import Tool


def _calendar_today(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    fixture_path_env = os.environ.get("EDITH_CALENDAR_FIXTURE")
    fixture_path = Path(fixture_path_env) if fixture_path_env else None
    source = select_source(edith_home=ctx.edith_home, fixture_path=fixture_path)
    return today_view(source)


CALENDAR_TODAY = Tool(
    name="calendar_today",
    description="오늘 캘린더 일정 list + 총 busy minutes. macOS면 Apple Calendar 직읽음.",
    input_schema={"type": "object", "properties": {}},
    fn=_calendar_today,
)
