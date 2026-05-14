"""calendar skill — F2 일정 수집."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import calendar

SKILL = Skill(
    name="calendar",
    scope="any",
    tools=[calendar.CALENDAR_TODAY],
    eval_globs=["evals/golden/f2_today_via_llm.yaml"],
    channels=["telegram"],
)
