"""Phase 3 F5 — Approval Queue.

LLM이 외부 write action을 요청하면 이 큐에 등록되고, 사용자가 `harness approve` CLI로
승인·거절. 승인 후 실제 실행은 feature별 executor가 담당 (per-feature 통합).

저장: harness/approvals.json (machine-local, gitignore).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "executed"]


@dataclass
class ApprovalRequest:
    id: str
    action_type: str  # 예: "calendar_create", "gmail_send", "github_workflow_update_cron"
    target_system: str  # 예: "google_calendar", "gmail", "github"
    preview: str  # 사용자가 보고 판단할 diff/text
    risk_score: int  # 1-10
    reversible: bool
    status: ApprovalStatus
    requested_at: str
    expires_at: str
    approved_by: str | None = None
    executed_at: str | None = None
    error: str | None = None

    @classmethod
    def new(
        cls,
        action_type: str,
        target_system: str,
        preview: str,
        risk_score: int = 5,
        reversible: bool = True,
        expires_minutes: int = 30,
    ) -> ApprovalRequest:
        now = datetime.now(UTC)
        return cls(
            id=str(uuid.uuid4())[:12],
            action_type=action_type,
            target_system=target_system,
            preview=preview,
            risk_score=risk_score,
            reversible=reversible,
            status="pending",
            requested_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=expires_minutes)).isoformat(),
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return now > datetime.fromisoformat(self.expires_at)


class ApprovalQueue:
    def __init__(self, queue_path: Path) -> None:
        self.path = queue_path

    def _load_all(self) -> list[ApprovalRequest]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [ApprovalRequest(**d) for d in data]
        except (json.JSONDecodeError, TypeError):
            return []

    def _save_all(self, requests: list[ApprovalRequest]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(r) for r in requests], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create(
        self,
        action_type: str,
        target_system: str,
        preview: str,
        risk_score: int = 5,
        reversible: bool = True,
        expires_minutes: int = 30,
    ) -> ApprovalRequest:
        req = ApprovalRequest.new(
            action_type=action_type,
            target_system=target_system,
            preview=preview,
            risk_score=risk_score,
            reversible=reversible,
            expires_minutes=expires_minutes,
        )
        all_ = self._load_all()
        all_.append(req)
        self._save_all(all_)
        return req

    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        all_ = self._load_all()
        if status:
            all_ = [r for r in all_ if r.status == status]
        return all_

    def get(self, id_: str) -> ApprovalRequest | None:
        for r in self._load_all():
            if r.id == id_:
                return r
        return None

    def approve(self, id_: str, approved_by: str = "user") -> ApprovalRequest:
        all_ = self._load_all()
        for r in all_:
            if r.id == id_:
                if r.status != "pending":
                    raise ValueError(f"approval {id_} status is {r.status}, cannot approve")
                if r.is_expired():
                    r.status = "expired"
                    self._save_all(all_)
                    raise ValueError(f"approval {id_} has expired")
                r.status = "approved"
                r.approved_by = approved_by
                self._save_all(all_)
                return r
        raise KeyError(id_)

    def reject(self, id_: str) -> ApprovalRequest:
        all_ = self._load_all()
        for r in all_:
            if r.id == id_:
                if r.status not in ("pending", "approved"):
                    raise ValueError(f"approval {id_} status is {r.status}, cannot reject")
                r.status = "rejected"
                self._save_all(all_)
                return r
        raise KeyError(id_)

    def mark_executed(self, id_: str, error: str | None = None) -> ApprovalRequest:
        all_ = self._load_all()
        for r in all_:
            if r.id == id_:
                if r.status != "approved":
                    raise ValueError(f"approval {id_} status is {r.status}, cannot mark executed")
                r.status = "executed"
                r.executed_at = datetime.now(UTC).isoformat()
                r.error = error
                self._save_all(all_)
                return r
        raise KeyError(id_)

    def expire_old(self) -> int:
        """pending 중 expires_at 지난 것을 expired 로 mark. expired 개수 반환."""
        all_ = self._load_all()
        n = 0
        now = datetime.now(UTC)
        for r in all_:
            if r.status == "pending" and r.is_expired(now):
                r.status = "expired"
                n += 1
        if n:
            self._save_all(all_)
        return n
