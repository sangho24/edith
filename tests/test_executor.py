"""F17 — ApprovalExecutor 테스트.

executor 함수를 registry로 inject해서 dispatch·상태 전이 로직을 검증.
github_workflow executor는 실제 YAML 파일을 수정하므로 end-to-end 검증.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.approval import ApprovalQueue, ApprovalRequest
from harness.executor import (
    ApprovalExecutor,
    ExecutionResult,
    _exec_github_workflow_update_cron,
    default_registry,
)


def _queue(tmp_path: Path) -> ApprovalQueue:
    return ApprovalQueue(tmp_path / "harness" / "approvals.json")


def _get(queue: ApprovalQueue, id_: str) -> ApprovalRequest:
    r = queue.get(id_)
    assert r is not None
    return r


# ── dispatch · 상태 전이 ─────────────────────────────────────────────────


def test_execute_success_marks_executed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("demo_action", "demo", "미리보기", params={"x": 1})
    queue.approve(req.id)

    calls: list[dict] = []

    def fake(r, home):  # noqa: ANN001
        calls.append(r.params)
        return ExecutionResult(ok=True, detail="했음")

    ex = ApprovalExecutor(queue, tmp_path, registry={"demo_action": fake})
    result = ex.execute(req.id)
    assert result.ok and result.detail == "했음"
    assert calls == [{"x": 1}]
    after = _get(queue, req.id)
    assert after.status == "executed"
    assert after.error is None


def test_execute_failure_records_error(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("demo_action", "demo", "p")
    queue.approve(req.id)

    ex = ApprovalExecutor(
        queue, tmp_path,
        registry={"demo_action": lambda r, h: ExecutionResult(ok=False, error="망함")},
    )
    result = ex.execute(req.id)
    assert not result.ok
    after = _get(queue, req.id)
    assert after.status == "executed"
    assert after.error == "망함"


def test_execute_catches_executor_exception(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("demo_action", "demo", "p")
    queue.approve(req.id)

    def boom(r, h):  # noqa: ANN001
        raise RuntimeError("터짐")

    ex = ApprovalExecutor(queue, tmp_path, registry={"demo_action": boom})
    result = ex.execute(req.id)
    assert not result.ok
    assert "RuntimeError" in result.error and "터짐" in result.error
    assert _get(queue, req.id).status == "executed"


def test_execute_no_executor_for_action(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("unknown_action", "x", "p")
    queue.approve(req.id)
    ex = ApprovalExecutor(queue, tmp_path, registry={})
    result = ex.execute(req.id)
    assert not result.ok
    assert "executor 없음" in result.error


def test_execute_rejects_non_approved(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("demo_action", "demo", "p")  # status=pending
    registry = {"demo_action": lambda r, h: ExecutionResult(True)}
    ex = ApprovalExecutor(queue, tmp_path, registry=registry)
    result = ex.execute(req.id)
    assert not result.ok
    assert "approved만" in result.error
    assert _get(queue, req.id).status == "pending"  # 안 건드림


def test_execute_unknown_id_raises(tmp_path: Path) -> None:
    ex = ApprovalExecutor(_queue(tmp_path), tmp_path, registry={})
    with pytest.raises(KeyError):
        ex.execute("nope12345")


# ── 실제 executor: github_workflow_update_cron ───────────────────────────

_WORKFLOW = """\
name: ds-digest
on:
  schedule:
    - cron: '10 22 * * *'
jobs:
  run:
    runs-on: ubuntu-latest
"""


def test_github_workflow_executor_changes_cron(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows" / "digest.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(_WORKFLOW, encoding="utf-8")

    queue = _queue(tmp_path)
    req = queue.create(
        "github_workflow_update_cron", "github",
        "cron 10 22 → 0 21",
        params={"workflow_path": ".github/workflows/digest.yml", "new_cron": "0 21 * * *"},
    )
    queue.approve(req.id)
    result = ApprovalExecutor(queue, tmp_path).execute(req.id)

    assert result.ok, result.error
    assert "0 21 * * *" in wf.read_text(encoding="utf-8")
    assert "10 22 * * *" not in wf.read_text(encoding="utf-8")
    assert _get(queue, req.id).status == "executed"


def test_github_workflow_executor_missing_params(tmp_path: Path) -> None:
    req = type("R", (), {"params": {}})()
    result = _exec_github_workflow_update_cron(req, tmp_path)  # type: ignore[arg-type]
    assert not result.ok
    assert "workflow_path" in result.error


def test_github_workflow_executor_absolute_path(tmp_path: Path) -> None:
    wf = tmp_path / "abs_digest.yml"
    wf.write_text(_WORKFLOW, encoding="utf-8")
    req = type("R", (), {"params": {"workflow_path": str(wf), "new_cron": "30 0 * * *"}})()
    result = _exec_github_workflow_update_cron(req, tmp_path)  # type: ignore[arg-type]
    assert result.ok
    assert "30 0 * * *" in wf.read_text(encoding="utf-8")


# ── 실제 executor: gmail_send (GmailSource monkeypatch) ──────────────────


def test_gmail_send_executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple] = []

    class FakeGmail:
        def __init__(self, *a, **kw) -> None:
            pass

        def send_message(self, to: str, subject: str, body: str) -> dict:
            sent.append((to, subject, body))
            return {"id": "msg-abc"}

    monkeypatch.setattr("harness.integrations.gmail.GmailSource", FakeGmail)

    queue = _queue(tmp_path)
    req = queue.create(
        "gmail_send", "gmail", "To: x@y.com",
        params={"to": "x@y.com", "subject": "안녕", "body": "본문"},
    )
    queue.approve(req.id)
    result = ApprovalExecutor(queue, tmp_path).execute(req.id)
    assert result.ok
    assert "msg-abc" in result.detail
    assert sent == [("x@y.com", "안녕", "본문")]


def test_gmail_send_executor_missing_params(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    req = queue.create("gmail_send", "gmail", "p", params={"to": "x@y.com"})
    queue.approve(req.id)
    result = ApprovalExecutor(queue, tmp_path).execute(req.id)
    assert not result.ok
    assert "to·subject·body" in result.error


def test_default_registry_has_known_actions() -> None:
    reg = default_registry()
    assert "github_workflow_update_cron" in reg
    assert "gmail_send" in reg
