"""propose_workflow tool — F28. LLM이 다단계 워크플로우를 근거와 함께 제안.

저장만 한다(proposed). 실행은 사용자가 GUI/Approvals에서 승인 후. 호출 자체는
policy.allow()의 F23 게이트(args.steps scope·PII 재귀 검사)를 통과해야 실행된다.
"""

from __future__ import annotations

from typing import Any

from harness.propose import ProposalStore, _step_from_dict
from harness.state import Context
from harness.tools import Tool


def _propose_workflow(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    raw_steps = args.get("steps", [])
    steps = [_step_from_dict(i + 1, s) for i, s in enumerate(raw_steps)]
    store = ProposalStore(ctx.edith_home / "harness" / "proposals.json")
    p = store.create(
        title=str(args.get("title", "(제목 없음)")),
        rationale=str(args.get("rationale", "")),
        scope=ctx.scope,
        steps=steps,
        trigger=str(args.get("trigger", "task")),
    )
    return {
        "proposal_id": p.id,
        "n_steps": len(p.steps),
        "title": p.title,
        "inferred_steps": [s.idx for s in p.steps if s.inferred],
        "note": "제안 등록됨 — GUI Proposals 탭에서 검토·승인. 승인 시 step별로 승인 큐로.",
    }


PROPOSE_WORKFLOW = Tool(
    name="propose_workflow",
    description=(
        "다단계 작업을 근거(support_refs)·예상결과·리스크와 함께 워크플로우로 제안한다. "
        "저장만 하며 실행하지 않음 — 사용자가 승인해야 step별로 승인 큐로 내려간다. "
        "근거 없는 step은 [추론]으로 표시되고 리스크가 상향된다."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "rationale": {"type": "string", "description": "이 워크플로우를 제안하는 이유"},
            "trigger": {"type": "string", "description": "task | morning_brief 등"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "explanation": {"type": "string"},
                        "expected_outcome": {"type": "string"},
                        "risk_note": {"type": "string"},
                        "support_refs": {"type": "array", "items": {"type": "string"}},
                        "action_type": {
                            "type": "string",
                            "description": "gmail_send 등 external / 빈값이면 internal",
                        },
                        "params": {"type": "object"},
                        "scope": {"type": "string", "description": "step scope (생략 시 제안 scope 상속)"},  # noqa: E501
                        "reversible": {"type": "boolean"},
                        "risk_score": {"type": "integer"},
                    },
                    "required": ["intent"],
                },
            },
        },
        "required": ["title", "steps"],
    },
    fn=_propose_workflow,
)


__all__ = ["PROPOSE_WORKFLOW"]
