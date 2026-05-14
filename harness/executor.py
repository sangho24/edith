"""F17 — Approval Executor.

승인된(status=approved) ApprovalRequest를 실제로 실행한다.

흐름: LLM이 request_approval → 큐에 pending → 사용자가 GUI/CLI로 승인 →
ApprovalExecutor.execute()가 action_type별 executor로 dispatch → 실행 후
queue.mark_executed (성공이면 error=None, 실패면 error 기록).

executor 함수는 registry로 주입 가능 (telegram.http_post / relay.forward_fn
패턴). 덕분에 dispatch·상태 전이 로직은 실제 외부 호출 없이 단위 테스트 가능.

ApprovalRequest.params가 executor의 입력 — preview는 사람용, params는 기계용.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness.approval import ApprovalQueue, ApprovalRequest

# executor: (승인된 요청, edith_home) → 실행 결과
ExecutorFn = Callable[[ApprovalRequest, Path], "ExecutionResult"]


@dataclass
class ExecutionResult:
    ok: bool
    detail: str = ""
    error: str = ""


# ── action_type별 executor ───────────────────────────────────────────────


def _exec_github_workflow_update_cron(
    req: ApprovalRequest, edith_home: Path
) -> ExecutionResult:
    """GitHub Actions workflow YAML의 cron 스케줄 변경.

    params: {workflow_path, new_cron, idx?}. workflow_path가 상대경로면
    edith_home 기준으로 해석. 커밋·push는 별도 (이 executor는 파일만 수정).
    """
    from harness.integrations.github_workflow import set_cron

    params = req.params
    raw_path = params.get("workflow_path")
    new_cron = params.get("new_cron")
    if not raw_path or not new_cron:
        return ExecutionResult(ok=False, error="params에 workflow_path·new_cron 필요")

    wf_path = Path(raw_path)
    if not wf_path.is_absolute():
        wf_path = edith_home / wf_path

    ok, detail = set_cron(wf_path, new_cron, int(params.get("idx", 0)))
    return ExecutionResult(ok=ok, detail=detail, error="" if ok else detail)


def _exec_gmail_send(req: ApprovalRequest, edith_home: Path) -> ExecutionResult:
    """Gmail 메일 발송. params: {to, subject, body}."""
    from harness.integrations.gmail import GmailSource

    params = req.params
    to, subject, body = params.get("to"), params.get("subject"), params.get("body")
    if not to or subject is None or body is None:
        return ExecutionResult(ok=False, error="params에 to·subject·body 필요")

    resp = GmailSource().send_message(to=to, subject=subject, body=body)
    return ExecutionResult(ok=True, detail=f"sent id={resp.get('id', '?')}")


def default_registry() -> dict[str, ExecutorFn]:
    """action_type → executor. 신규 외부 action은 여기 한 줄 추가."""
    return {
        "github_workflow_update_cron": _exec_github_workflow_update_cron,
        "gmail_send": _exec_gmail_send,
    }


# ── 실행 오케스트레이터 ──────────────────────────────────────────────────


class ApprovalExecutor:
    """승인된 요청을 dispatch해서 실행하고 큐 상태를 갱신."""

    def __init__(
        self,
        queue: ApprovalQueue,
        edith_home: Path,
        registry: dict[str, ExecutorFn] | None = None,
    ) -> None:
        self.queue = queue
        self.edith_home = edith_home
        self.registry = registry if registry is not None else default_registry()

    def execute(self, request_id: str) -> ExecutionResult:
        """승인된 요청 1건 실행. status=approved가 아니면 거부.

        실행 후 queue.mark_executed — 성공이면 error=None, 실패면 error 기록.
        executor가 던진 예외도 잡아서 ExecutionResult.error로.
        """
        req = self.queue.get(request_id)
        if req is None:
            raise KeyError(request_id)
        if req.status != "approved":
            return ExecutionResult(
                ok=False, error=f"status가 '{req.status}' — approved만 실행 가능"
            )

        fn = self.registry.get(req.action_type)
        if fn is None:
            result = ExecutionResult(
                ok=False, error=f"'{req.action_type}'에 등록된 executor 없음"
            )
        else:
            try:
                result = fn(req, self.edith_home)
            except Exception as e:  # noqa: BLE001 — executor 예외를 결과로 흡수
                result = ExecutionResult(ok=False, error=f"{type(e).__name__}: {e}")

        self.queue.mark_executed(
            request_id, error=None if result.ok else (result.error or "execution failed")
        )
        return result
