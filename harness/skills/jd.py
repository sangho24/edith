"""jd skill — F9 채용공고 분석."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import jd

SKILL = Skill(
    name="jd",
    scope="personal",
    tools=[jd.JD_ANALYZE],
    eval_globs=[],
)
