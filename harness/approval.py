"""Phase 3 F5 — Approval Queue.

LLM이 외부 write action을 요청하면 이 큐에 등록되고, 사용자가 `harness approve` CLI로
승인·거절. 승인 후 실제 실행은 feature별 executor가 담당 (per-feature 통합).

저장: harness/approvals.json (machine-local, gitignore).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from harness.storage import atomic_write_json, file_lock, read_json_file

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
    # 실행에 필요한 구조화된 인자. executor가 이걸 보고 실제 action 수행.
    # preview는 사람용, params는 기계용. 비어있으면 executor가 실행 불가.
    params: dict = field(default_factory=dict)
    # F21 — 이 action이 속한 scope (personal|school|work|mixed). request_approval이
    # ctx.scope를 전달. memory feedback·pattern·trace 감사가 scope별 격리하려면 필요.
    # 하위호환: 기존 직렬화 레코드엔 없으므로 default "personal".
    scope: str = "personal"

    @classmethod
    def new(
        cls,
        action_type: str,
        target_system: str,
        preview: str,
        risk_score: int = 5,
        reversible: bool = True,
        expires_minutes: int = 30,
        params: dict | None = None,
        scope: str = "personal",
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
            params=params or {},
            scope=scope,
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return now > datetime.fromisoformat(self.expires_at)


class ApprovalQueue:
    def __init__(self, queue_path: Path) -> None:
        self.path = queue_path

    def _load_all(self) -> list[ApprovalRequest]:
        try:
            data = read_json_file(self.path, [])
            return [ApprovalRequest(**d) for d in data]
        except TypeError:
            return []

    def _save_all(self, requests: list[ApprovalRequest]) -> None:
        atomic_write_json(self.path, [asdict(r) for r in requests])

    def create(
        self,
        action_type: str,
        target_system: str,
        preview: str,
        risk_score: int = 5,
        reversible: bool = True,
        expires_minutes: int = 30,
        params: dict | None = None,
        scope: str = "personal",
    ) -> ApprovalRequest:
        req = ApprovalRequest.new(
            action_type=action_type,
            target_system=target_system,
            preview=preview,
            risk_score=risk_score,
            reversible=reversible,
            expires_minutes=expires_minutes,
            params=params,
            scope=scope,
        )
        with file_lock(self.path):
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
        with file_lock(self.path):
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
        with file_lock(self.path):
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
        with file_lock(self.path):
            all_ = self._load_all()
            for r in all_:
                if r.id == id_:
                    if r.status != "approved":
                        raise ValueError(
                            f"approval {id_} status is {r.status}, cannot mark executed"
                        )
                    r.status = "executed"
                    r.executed_at = datetime.now(UTC).isoformat()
                    r.error = error
                    self._save_all(all_)
                    return r
        raise KeyError(id_)

    def expire_old(self) -> int:
        """pending 중 expires_at 지난 것을 expired 로 mark. expired 개수 반환."""
        with file_lock(self.path):
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
