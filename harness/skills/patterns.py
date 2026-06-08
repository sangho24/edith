"""patterns skill — recurring task detection."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import patterns

SKILL = Skill(
    name="patterns",
    scope="any",
    tools=[patterns.PATTERN_MATCH, patterns.PATTERN_LIST],
    eval_globs=[
        "evals/golden/t3_patterns_support.yaml",
        "evals/golden/t3_patterns_jaccard_split.yaml",
    ],
)
