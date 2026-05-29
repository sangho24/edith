"""proposal skill — F28 워크플로우 제안.

propose_workflow tool을 묶는 manifest. scope=any (제안 자체는 안전, step 실행은
ApprovalQueue + executor가 게이트). 호출은 policy F23 게이트를 통과해야 함.
"""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import propose

SKILL = Skill(
    name="proposal",
    scope="any",
    tools=[propose.PROPOSE_WORKFLOW],
    eval_globs=[
        "evals/golden/f28_propose_basic.yaml",
        "evals/golden/f28_propose_citation.yaml",
        "evals/golden/f28_no_autosend.yaml",
    ],
    channels=[],
)
