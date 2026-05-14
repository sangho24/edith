"""recall skill — F6 메모리 회상 (support_refs 첨부)."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import recall

SKILL = Skill(
    name="recall",
    scope="any",
    tools=[recall.MEMORY_RECALL],
    eval_globs=["evals/golden/f6_recall.yaml"],
)
