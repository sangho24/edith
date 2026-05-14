"""health skill — F15 Apple Health 데이터.

scope=personal 고정. Edith가 다루는 가장 민감한 데이터 — cross-scope retrieve 금지.
정책 게이트: skill scope가 personal이므로 work/school task에서 health_summary가
호출되면 policies.allow()의 R3 룰로 차단된다 (f15_health_scope_block.yaml로 검증).
"""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import health

SKILL = Skill(
    name="health",
    scope="personal",
    tools=[health.HEALTH_SUMMARY],
    eval_globs=[
        "evals/golden/f15_health.yaml",
        "evals/golden/f15_health_scope_block.yaml",
    ],
)
