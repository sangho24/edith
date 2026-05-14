"""papers skill — F8 arXiv 논문 triage."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import paper

SKILL = Skill(
    name="papers",
    scope="any",
    tools=[paper.PAPER_TRIAGE],
    eval_globs=[],
)
