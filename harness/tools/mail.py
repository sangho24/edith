"""mail_triage tool — F3 LLM 통합.

LLM이 "오늘 답해야 할 메일?" task를 받으면 이 tool 호출.
select_mail_source가 EDITH_MAIL_BACKEND=gmail(실연동)·EDITH_MAIL_FIXTURE·local(raw)을 분기.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from harness.mail import select_mail_source, triage
from harness.state import Context
from harness.tools import Tool


def _mail_triage(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    source = select_mail_source(ctx.edith_home)
    limit = int(args.get("limit", 50))
    messages = source.list_unread(limit=limit)
    items = triage(messages)
    counts = Counter(i.priority for i in items)
    return {
        "n_unread": len(items),
        "by_priority": dict(counts),
        "items": [
            {
                "id": i.message.id,
                "sender": i.message.sender,
                "subject": i.message.subject,
                "priority": i.priority,
                "received_at": i.message.received_at.isoformat(),
            }
            for i in items
        ],
    }


MAIL_TRIAGE = Tool(
    name="mail_triage",
    description=(
        "읽지 않은 메일 priority 분류 (urgent/important/notification/newsletter/normal). read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 50, "description": "최대 메시지 수"},
        },
    },
    fn=_mail_triage,
)


def _mail_search(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query 필요"}
    limit = int(args.get("limit", 20))
    source = select_mail_source(ctx.edith_home)
    try:
        items = source.search(query, limit=limit)
    except Exception as e:  # noqa: BLE001 — 검색 실패를 결과로 흡수
        return {"error": f"검색 실패: {type(e).__name__}: {e}"}
    return {
        "query": query,
        "n": len(items),
        "items": [
            {
                "id": m.id,
                "sender": m.sender,
                "subject": m.subject,
                "received_at": m.received_at.isoformat(),
                "unread": m.unread,
            }
            for m in items
        ],
    }


MAIL_SEARCH = Tool(
    name="mail_search",
    description=(
        "메일 검색 — 읽음·안읽음·과거 메일 모두. Gmail 검색 문법 지원 "
        "(예: 'from:비씨카드', 'subject:결과', '계약서', 'newer_than:7d'). read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색어 (Gmail 검색 문법 가능)"},
            "limit": {"type": "integer", "default": 20, "description": "최대 결과 수"},
        },
        "required": ["query"],
    },
    fn=_mail_search,
)
