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
    """approval queue placeholder. Phase 3 F5에서 풀 구현."""
    return {
        "queued": True,
        "queue_id": f"pending-{datetime.now(UTC).timestamp():.0f}",
        "note": "approval queue는 Phase 3 F5에서 풀 구현. 지금은 placeholder.",
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
    description="외부 발송 등 비가역 액션을 승인 큐에 등록. preview 필수.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "preview": {"type": "string"},
            "reversible": {"type": "boolean", "default": False},
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
