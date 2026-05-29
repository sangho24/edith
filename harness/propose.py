"""F28 — 워크플로우 제안 + 납득 설명 레이어.

LLM이 "이렇게 처리하면 됩니다"를 단계별 워크플로우로 제안하고, 각 step에 근거
(support_refs)·예상결과·리스크를 붙인다. ApprovalRequest를 깨지 않고 그 위에 얹는다:
proposed 상태로 저장 → 사용자가 GUI에서 보고 (부분)승인 → 승인된 step별로
ApprovalQueue에 내려가 → ApprovalExecutor(F17)가 실행.

PRD docs/08 §4.4. "승인만"(B5 executor와 디커플) — accept는 ApprovalRequest를
pending으로 만들 뿐, 자동 실행하지 않는다(L2→L3은 Approvals 탭에서).

안전: propose_workflow tool 호출은 policy.allow()의 F23 게이트가 args.steps를
재귀 검사(scope 교차·PII)한 뒤에야 실행된다.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ProposalStatus = Literal["proposed", "closed"]

# support_refs 없는 step은 추론으로 간주하고 리스크를 이 값 이상으로 올린다(인용 규율).
INFERRED_MIN_RISK = 6


@dataclass
class ProposalStep:
    idx: int
    intent: str
    explanation: str = ""
    expected_outcome: str = ""
    risk_note: str = ""
    support_refs: list[str] = field(default_factory=list)
    action_type: str = ""  # "" = internal/없음, 또는 gmail_send 등 external
    params: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    risk_score: int = 3
    inferred: bool = False
    queued_approval_id: str | None = None

    def preview(self) -> str:
        """사용자가 보고 판단할 한 step의 텍스트 (설명+예상+근거)."""
        cite = ", ".join(self.support_refs) if self.support_refs else "[추론 — 근거 없음]"
        lines = [f"{self.idx}. {self.intent}"]
        if self.explanation:
            lines.append(f"   설명: {self.explanation}")
        if self.expected_outcome:
            lines.append(f"   예상결과: {self.expected_outcome}")
        if self.risk_note:
            lines.append(f"   리스크: {self.risk_note}")
        lines.append(f"   근거: {cite}  (risk {self.risk_score}, "
                     f"{'가역' if self.reversible else '비가역'})")
        return "\n".join(lines)


@dataclass
class Proposal:
    id: str
    title: str
    trigger: str  # "task" | "morning_brief" | ...
    rationale: str
    scope: str
    steps: list[ProposalStep]
    status: ProposalStatus
    created_at: str

    @classmethod
    def new(
        cls,
        title: str,
        rationale: str,
        scope: str,
        steps: list[ProposalStep],
        trigger: str = "task",
    ) -> Proposal:
        return cls(
            id=str(uuid.uuid4())[:12],
            title=title,
            trigger=trigger,
            rationale=rationale,
            scope=scope,
            steps=steps,
            status="proposed",
            created_at=datetime.now(UTC).isoformat(),
        )

    def render(self) -> str:
        """제안 전체를 사람이 읽는 텍스트로."""
        head = f"📋 제안: {self.title}  (scope={self.scope})"
        if self.rationale:
            head += f"\n근거: {self.rationale}"
        body = "\n".join(s.preview() for s in self.steps)
        return f"{head}\n\n{body}"


def _step_from_dict(idx: int, d: dict[str, Any]) -> ProposalStep:
    """tool args의 step dict → ProposalStep. 근거 없으면 inferred + 리스크 상향."""
    support_refs = list(d.get("support_refs", []) or [])
    risk = int(d.get("risk_score", 3))
    inferred = not support_refs
    if inferred:
        risk = max(risk, INFERRED_MIN_RISK)
    return ProposalStep(
        idx=idx,
        intent=str(d.get("intent", "")),
        explanation=str(d.get("explanation", "")),
        expected_outcome=str(d.get("expected_outcome", "")),
        risk_note=str(d.get("risk_note", "")),
        support_refs=support_refs,
        action_type=str(d.get("action_type", "")),
        params=dict(d.get("params", {})),
        reversible=bool(d.get("reversible", True)),
        risk_score=risk,
        inferred=inferred,
    )


class ProposalStore:
    """proposals.json 영속화 (ApprovalQueue 패턴)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> list[Proposal]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        out: list[Proposal] = []
        for d in data:
            steps = [ProposalStep(**s) for s in d.get("steps", [])]
            out.append(Proposal(**{**d, "steps": steps}))
        return out

    def _save(self, proposals: list[Proposal]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(p) for p in proposals], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(
        self, title: str, rationale: str, scope: str,
        steps: list[ProposalStep], trigger: str = "task",
    ) -> Proposal:
        p = Proposal.new(title, rationale, scope, steps, trigger)
        all_ = self._load()
        all_.append(p)
        self._save(all_)
        return p

    def list(self, status: ProposalStatus | None = None) -> list[Proposal]:
        all_ = self._load()
        return [p for p in all_ if status is None or p.status == status]

    def get(self, id_: str) -> Proposal | None:
        return next((p for p in self._load() if p.id == id_), None)

    def close(self, id_: str) -> Proposal | None:
        all_ = self._load()
        for p in all_:
            if p.id == id_:
                p.status = "closed"
                self._save(all_)
                return p
        return None
