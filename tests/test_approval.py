"""Phase 3 F5 — Approval queue tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from harness.approval import ApprovalQueue


@pytest.fixture
def queue(tmp_path: Path) -> ApprovalQueue:
    return ApprovalQueue(tmp_path / "approvals.json")


def test_create_pending(queue: ApprovalQueue) -> None:
    req = queue.create(
        action_type="calendar_create",
        target_system="google_calendar",
        preview="title: 회의\nstart: 2026-04-29 10:00",
    )
    assert req.status == "pending"
    assert req.id
    assert req.risk_score == 5
    assert req.reversible is True
    assert req.scope == "personal"  # F21 default


# ── F21 per-item scope ───────────────────────────────────────────────────


def test_create_records_scope(queue: ApprovalQueue) -> None:
    req = queue.create("gmail_send", "gmail", "p", scope="work")
    assert req.scope == "work"
    # 영속 후에도 보존
    fetched = queue.get(req.id)
    assert fetched is not None and fetched.scope == "work"


def test_request_approval_tool_stamps_ctx_scope(tmp_path: Path) -> None:
    """request_approval tool이 ctx.scope를 승인 요청에 각인 (F21)."""
    from harness.state import Context, Trace
    from harness.tools.util import _request_approval

    (tmp_path / "harness").mkdir()
    ctx = Context(edith_home=tmp_path, scope="work", trace=Trace.start("t", scope="work"))
    out = _request_approval(
        {"action": "gmail_send", "preview": "메일", "params": {"to": "x@y.com"}}, ctx
    )
    assert out["queued"]
    q = ApprovalQueue(tmp_path / "harness" / "approvals.json")
    fetched = q.get(out["queue_id"])
    assert fetched is not None and fetched.scope == "work"


def test_legacy_record_without_scope_defaults_personal(tmp_path: Path) -> None:
    """scope 필드 없던 구버전 approvals.json 로드 시 default personal (하위호환)."""
    import json

    p = tmp_path / "approvals.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "legacy123",
                    "action_type": "gmail_send",
                    "target_system": "gmail",
                    "preview": "old",
                    "risk_score": 5,
                    "reversible": True,
                    "status": "pending",
                    "requested_at": "2026-05-01T00:00:00+00:00",
                    "expires_at": "2026-05-01T00:30:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    q = ApprovalQueue(p)
    legacy = q.get("legacy123")
    assert legacy is not None and legacy.scope == "personal"


def test_list_filters_by_status(queue: ApprovalQueue) -> None:
    queue.create("calendar_create", "google_calendar", "p1")
    queue.create("gmail_send", "gmail", "p2")
    queue.create("github_commit", "github", "p3")

    pending = queue.list(status="pending")
    assert len(pending) == 3

    queue.approve(pending[0].id)
    assert len(queue.list(status="pending")) == 2
    assert len(queue.list(status="approved")) == 1


def test_get_by_id(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    fetched = queue.get(req.id)
    assert fetched is not None
    assert fetched.id == req.id
    assert queue.get("nonexistent") is None


def test_approve_pending(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    approved = queue.approve(req.id, approved_by="sangho")
    assert approved.status == "approved"
    assert approved.approved_by == "sangho"


def test_approve_already_approved_fails(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    queue.approve(req.id)
    with pytest.raises(ValueError) as exc:
        queue.approve(req.id)
    assert "approved" in str(exc.value)


def test_approve_expired_fails(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z", expires_minutes=0)
    time.sleep(0.05)  # expires_at은 created_at 시각이라 0분 지나면 즉시 expired
    with pytest.raises(ValueError) as exc:
        queue.approve(req.id)
    assert "expired" in str(exc.value)


def test_reject_pending(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    rejected = queue.reject(req.id)
    assert rejected.status == "rejected"


def test_reject_executed_fails(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    queue.approve(req.id)
    queue.mark_executed(req.id)
    with pytest.raises(ValueError):
        queue.reject(req.id)


def test_mark_executed(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    queue.approve(req.id)
    executed = queue.mark_executed(req.id)
    assert executed.status == "executed"
    assert executed.executed_at is not None


def test_mark_executed_with_error(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    queue.approve(req.id)
    executed = queue.mark_executed(req.id, error="API timeout")
    assert executed.error == "API timeout"


def test_mark_executed_requires_approved(queue: ApprovalQueue) -> None:
    req = queue.create("x", "y", "z")
    with pytest.raises(ValueError):
        queue.mark_executed(req.id)


def test_expire_old_marks_pending_expired(queue: ApprovalQueue) -> None:
    req1 = queue.create("x", "y", "z", expires_minutes=0)
    req2 = queue.create("x", "y", "z", expires_minutes=30)
    time.sleep(0.05)
    n = queue.expire_old()
    assert n == 1
    assert queue.get(req1.id).status == "expired"  # type: ignore
    assert queue.get(req2.id).status == "pending"  # type: ignore


def test_persistence_across_instances(tmp_path: Path) -> None:
    """다른 인스턴스가 같은 파일 읽을 수 있어야."""
    p = tmp_path / "approvals.json"
    q1 = ApprovalQueue(p)
    req = q1.create("x", "y", "z")
    q2 = ApprovalQueue(p)
    fetched = q2.get(req.id)
    assert fetched is not None
    assert fetched.action_type == "x"


def test_two_queue_instances_create_preserves_both_requests(tmp_path: Path) -> None:
    """read-modify-write가 인스턴스별로 이어져도 두 create 모두 보존."""
    p = tmp_path / "approvals.json"
    q1 = ApprovalQueue(p)
    q2 = ApprovalQueue(p)

    r1 = q1.create("gmail_send", "gmail", "one")
    r2 = q2.create("gmail_send", "gmail", "two")

    ids = {r.id for r in ApprovalQueue(p).list()}
    assert ids == {r1.id, r2.id}


def test_corrupt_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "approvals.json"
    p.write_text("{not valid json", encoding="utf-8")
    queue = ApprovalQueue(p)
    assert queue.list() == []


def test_l3_simulation_no_auto_send(queue: ApprovalQueue) -> None:
    """F5 머지 기준: 10 calendar event 초안 → 미승인 자동 발송 0건."""
    requests = []
    for i in range(10):
        r = queue.create(
            "calendar_create",
            "google_calendar",
            f"event {i}: 회의 {i + 1}",
            risk_score=4,
            reversible=True,
        )
        requests.append(r)
    # 자동 발송 없음 — 모두 pending 상태
    assert all(r.status == "pending" for r in queue.list())
    auto_executed = [r for r in queue.list(status="executed")]
    assert auto_executed == []
