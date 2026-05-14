"""repo skill — F7 PR 1차 리뷰."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import pr

SKILL = Skill(
    name="repo",
    scope="any",
    tools=[pr.PR_REVIEW],
    eval_globs=[],
)
