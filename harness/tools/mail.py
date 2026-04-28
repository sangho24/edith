"""mail_triage tool — F3 LLM 통합.

LLM이 "오늘 답해야 할 메일?" task를 받으면 이 tool 호출.
EDITH_MAIL_FIXTURE 환경변수 또는 raw/mail/messages.json 에서 읽기.
F3.x에서 GmailSource 우선 사용으로 전환.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from harness.mail import LocalMessageSource, triage
from harness.state import Context
from harness.tools import Tool


def _mail_triage(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    fixture_path_env = os.environ.get("EDITH_MAIL_FIXTURE")
    fixture_path = (
        Path(fixture_path_env)
        if fixture_path_env
        else ctx.edith_home / "raw" / "mail" / "messages.json"
    )
    source = LocalMessageSource(fixture_path)
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
