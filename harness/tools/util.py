"""query_db, request_approval, emit_log — Phase 1 placeholders."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from harness.state import Context
from harness.tools import Tool


def _query_db(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """personal.db SQLite 쿼리. Phase 1 placeholder — DB 없으면 빈 결과."""
    db_path = ctx.edith_home / "personal.db"
    if not db_path.exists():
        return {"rows": [], "n": 0, "note": "personal.db 없음 — H6에서 만듦"}

    import sqlite3

    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(args["sql"])
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
        return {"rows": rows, "n": len(rows)}
    except Exception as e:
        return {"rows": [], "error": str(e)}


def _request_approval(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """외부 write action을 ApprovalQueue에 등록 (F5/F17).

    preview는 사람이 보고 판단, params는 executor가 실제 실행에 쓰는 구조화 인자.
    params 없이 등록되면 승인돼도 executor가 실행 불가.
    """
    from harness.approval import ApprovalQueue

    queue = ApprovalQueue(ctx.edith_home / "harness" / "approvals.json")
    req = queue.create(
        action_type=args["action"],
        target_system=args.get("target_system", ""),
        preview=args["preview"],
        risk_score=args.get("risk_score", 5),
        reversible=args.get("reversible", True),
        expires_minutes=args.get("expires_minutes", 30),
        params=args.get("params", {}),
        scope=ctx.scope,  # F21 — task scope를 승인 요청에 각인 (scope별 격리·감사)
    )
    return {
        "queued": True,
        "queue_id": req.id,
        "status": req.status,
        "note": "사용자 승인 후 executor가 실행. GUI Approvals 탭 또는 `harness approve`.",
    }


def _emit_log(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    level = args.get("level", "info")
    msg = args["msg"]
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {level.upper()}: {msg}")
    return {"ok": True}


QUERY_DB = Tool(
    name="query_db",
    description="personal.db SQLite read-only 쿼리. Phase 1엔 DB 없을 수 있음.",
    input_schema={
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
    fn=_query_db,
)

REQUEST_APPROVAL = Tool(
    name="request_approval",
    description=(
        "외부 발송 등 비가역 액션을 승인 큐에 등록 (F5). "
        "사용자가 CLI에서 승인·거절. action_type / preview 필수."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "action_type, e.g., gmail_send"},
            "target_system": {"type": "string", "description": "google_calendar, gmail 등"},
            "preview": {
                "type": "string",
                "description": "변경 내용 diff/text — 사용자가 보고 판단",
            },
            "params": {
                "type": "object",
                "description": (
                    "executor가 실제 실행에 쓰는 구조화 인자. "
                    "예: gmail_send → {to, subject, body}"
                ),
            },
            "risk_score": {"type": "integer", "default": 5, "description": "1-10"},
            "reversible": {"type": "boolean", "default": True},
            "expires_minutes": {"type": "integer", "default": 30},
        },
        "required": ["action", "preview"],
    },
    fn=_request_approval,
)

EMIT_LOG = Tool(
    name="emit_log",
    description="observability 로그 한 줄 출력 (level: info|warn|error).",
    input_schema={
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "enum": ["info", "warn", "error"],
            },
            "msg": {"type": "string"},
        },
        "required": ["msg"],
    },
    fn=_emit_log,
)
