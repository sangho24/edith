"""F28 — 워크플로우 제안 store·tool·decide 테스트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.propose import INFERRED_MIN_RISK, ProposalStore, _step_from_dict
from harness.state import Context, Trace
from harness.tools.propose import _propose_workflow


def _ctx(tmp_path: Path, scope: str = "personal") -> Context:
    (tmp_path / "harness").mkdir(exist_ok=True)
    return Context(edith_home=tmp_path, scope=scope, trace=Trace.start("t"))  # type: ignore[arg-type]


# ── _step_from_dict 인용 규율 ────────────────────────────────────────────


def test_step_with_refs_not_inferred() -> None:
    s = _step_from_dict(1, {"intent": "x", "support_refs": ["raw/a.md"], "risk_score": 2})
    assert s.inferred is False
    assert s.risk_score == 2


def test_step_without_refs_is_inferred_and_risk_bumped() -> None:
    s = _step_from_dict(1, {"intent": "x", "risk_score": 2})
    assert s.inferred is True
    assert s.risk_score >= INFERRED_MIN_RISK


def test_step_preview_marks_inference() -> None:
    s = _step_from_dict(1, {"intent": "메일"})
    assert "[추론" in s.preview()


# ── ProposalStore ────────────────────────────────────────────────────────


def test_store_create_and_list(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path / "proposals.json")
    step = _step_from_dict(1, {"intent": "a", "support_refs": ["r"]})
    p = store.create("t", "이유", "personal", [step])
    assert p.status == "proposed"
    assert len(store.list(status="proposed")) == 1
    assert store.get(p.id) is not None


def test_store_close(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path / "proposals.json")
    p = store.create("t", "", "personal", [])
    store.close(p.id)
    assert store.list(status="proposed") == []
    closed = store.get(p.id)
    assert closed is not None and closed.status == "closed"


def test_store_roundtrip_persists_steps(tmp_path: Path) -> None:
    path = tmp_path / "proposals.json"
    s1 = ProposalStore(path)
    p = s1.create("t", "", "work", [_step_from_dict(1, {"intent": "a", "action_type": "gmail_send",
                                                        "support_refs": ["r"]})])
    # 새 인스턴스로 다시 로드
    s2 = ProposalStore(path)
    got = s2.get(p.id)
    assert got is not None
    assert got.scope == "work"
    assert got.steps[0].action_type == "gmail_send"


def test_two_store_instances_create_preserves_both_proposals(tmp_path: Path) -> None:
    path = tmp_path / "proposals.json"
    step = _step_from_dict(1, {"intent": "a", "support_refs": ["r"]})
    p1 = ProposalStore(path).create("one", "", "personal", [step])
    p2 = ProposalStore(path).create("two", "", "personal", [step])

    ids = {p.id for p in ProposalStore(path).list()}
    assert ids == {p1.id, p2.id}


# ── propose_workflow tool ────────────────────────────────────────────────


def test_propose_tool_creates_proposal(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    out = _propose_workflow(
        {
            "title": "리뷰 처리",
            "steps": [
                {"intent": "캘린더 블록", "action_type": "calendar_create",
                 "support_refs": ["raw/x.md"], "risk_score": 3},
                {"intent": "초안 작성", "action_type": ""},  # 근거 없음 → inferred
            ],
        },
        ctx,
    )
    assert out["n_steps"] == 2
    assert 2 in out["inferred_steps"]  # 두 번째 step은 근거 없음
    store = ProposalStore(tmp_path / "harness" / "proposals.json")
    assert store.get(out["proposal_id"]) is not None


def test_propose_tool_uses_ctx_scope(tmp_path: Path) -> None:
    out = _propose_workflow({"title": "t", "steps": [{"intent": "a"}]}, _ctx(tmp_path, "work"))
    store = ProposalStore(tmp_path / "harness" / "proposals.json")
    p = store.get(out["proposal_id"])
    assert p is not None and p.scope == "work"


# ── server decide 엔드포인트 (accept → ApprovalQueue) ────────────────────


def _client(tmp_path: Path) -> Any:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from harness.server import make_app

    for sub in ("harness",):
        (tmp_path / sub).mkdir(exist_ok=True)
    return TestClient(make_app(edith_home=tmp_path, secret="s"))


def _seed_proposal(tmp_path: Path) -> str:
    store = ProposalStore(tmp_path / "harness" / "proposals.json")
    p = store.create(
        "메일+캘린더", "", "personal",
        [
            _step_from_dict(1, {"intent": "캘린더", "action_type": "calendar_create",
                                "support_refs": ["r"], "params": {"title": "x"}, "risk_score": 3}),
            _step_from_dict(2, {"intent": "메모", "action_type": "", "support_refs": ["r"]}),
        ],
    )
    return p.id


def test_ui_proposals_lists(tmp_path: Path) -> None:
    _seed_proposal(tmp_path)
    data = _client(tmp_path).get("/ui/proposals").json()
    assert data["ok"]
    assert len(data["proposals"]) == 1
    assert data["proposals"][0]["steps"][0]["action_type"] == "calendar_create"


def test_ui_proposals_accept_creates_approvals(tmp_path: Path) -> None:
    pid = _seed_proposal(tmp_path)
    client = _client(tmp_path)
    resp = client.post("/ui/proposals/decide", json={"id": pid, "decision": "accept"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    # external step(calendar_create) 1개만 큐로, internal step은 제외
    assert len(data["queued_approvals"]) == 1
    # 승인 큐에 실제로 등록됨
    from harness.approval import ApprovalQueue

    q = ApprovalQueue(tmp_path / "harness" / "approvals.json")
    pending = q.list(status="pending")
    assert len(pending) == 1
    assert pending[0].action_type == "calendar_create"
    assert pending[0].scope == "personal"


def test_ui_proposals_partial_accept(tmp_path: Path) -> None:
    pid = _seed_proposal(tmp_path)
    client = _client(tmp_path)
    # step 2만 승인 (internal이라 큐 0건)
    resp = client.post(
        "/ui/proposals/decide",
        json={"id": pid, "decision": "accept", "accepted_steps": [2]},
    )
    assert resp.json()["queued_approvals"] == []


def test_ui_proposals_reject(tmp_path: Path) -> None:
    pid = _seed_proposal(tmp_path)
    client = _client(tmp_path)
    resp = client.post("/ui/proposals/decide", json={"id": pid, "decision": "reject"})
    assert resp.json()["status"] == "rejected"
    # 처리 후 목록에서 사라짐
    assert client.get("/ui/proposals").json()["proposals"] == []


def test_ui_proposals_decide_bad_input(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post("/ui/proposals/decide", json={"id": "x"}).status_code == 400


def test_ui_proposals_no_autosend(tmp_path: Path) -> None:
    """accept해도 executor는 안 돈다 — 큐에 pending으로만 (실행은 Approvals)."""
    pid = _seed_proposal(tmp_path)
    client = _client(tmp_path)
    client.post("/ui/proposals/decide", json={"id": pid, "decision": "accept"})
    from harness.approval import ApprovalQueue

    q = ApprovalQueue(tmp_path / "harness" / "approvals.json")
    assert all(r.status == "pending" for r in q.list())  # executed 아님
