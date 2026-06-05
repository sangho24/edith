"""Phase 3 F3 — Mail Triage.

MessageSource ABC + LocalMessageSource (JSON fixture) + GmailSource (placeholder).

priority 분류 룰: urgent / important / notification / newsletter / normal.
머지 기준: 50개 mock 메일 정확도 ≥85%.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, get_args

Priority = Literal["urgent", "important", "notification", "newsletter", "normal"]
PRIORITY_ORDER: tuple[Priority, ...] = get_args(Priority)


@dataclass
class Message:
    id: str
    sender: str
    subject: str
    snippet: str
    received_at: datetime
    labels: list[str]
    unread: bool = True
    thread_id: str | None = None


class MessageSource(ABC):
    @abstractmethod
    def list_unread(self, limit: int = 50) -> list[Message]: ...


class LocalMessageSource(MessageSource):
    """JSON fixture에서 메시지 로드 (test/dev)."""

    def __init__(self, messages_path: Path) -> None:
        self.messages_path = messages_path

    def list_unread(self, limit: int = 50) -> list[Message]:
        if not self.messages_path.exists():
            return []
        try:
            data = json.loads(self.messages_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        msgs: list[Message] = []
        for item in data:
            msgs.append(
                Message(
                    id=item["id"],
                    sender=item["sender"],
                    subject=item.get("subject", ""),
                    snippet=item.get("snippet", ""),
                    received_at=datetime.fromisoformat(item["received_at"]),
                    labels=item.get("labels", []),
                    unread=item.get("unread", True),
                    thread_id=item.get("thread_id"),
                )
            )
        msgs = [m for m in msgs if m.unread]
        msgs.sort(key=lambda m: m.received_at, reverse=True)
        return msgs[:limit]


def _gmail_to_message(mm: Any) -> Message:
    """integrations.gmail.MailMessage → F3 triage용 Message."""
    return Message(
        id=mm.id,
        sender=mm.sender,
        subject=mm.subject,
        snippet=mm.snippet,
        received_at=mm.date,
        labels=list(mm.labels),
        unread=mm.is_unread,
        thread_id=mm.thread_id,
    )


class GmailMessageSource(MessageSource):
    """실 Gmail(integrations.gmail.GmailSource)을 F3 Message 인터페이스로 어댑트.

    실 호출은 google_auth 단일 토큰 필요(`harness oauth google`). 테스트는 source 주입
    (MockMailSource 등)으로 라이브러리/토큰 없이 검증.
    """

    def __init__(self, source: Any = None) -> None:
        self._source = source

    def _src(self) -> Any:
        if self._source is None:
            from harness.integrations.gmail import GmailSource

            self._source = GmailSource()
        return self._source

    def list_unread(self, limit: int = 50) -> list[Message]:
        return [_gmail_to_message(mm) for mm in self._src().list_unread(max_results=limit)]


def select_mail_source(edith_home: Path) -> MessageSource:
    """환경에 맞는 메일 source 선택.

    1. EDITH_MAIL_FIXTURE → LocalMessageSource (테스트/시연 override)
    2. EDITH_MAIL_BACKEND=gmail → GmailMessageSource (실 Gmail 연동)
    3. fallback → LocalMessageSource(edith_home/raw/mail/messages.json)
    """
    fixture = os.environ.get("EDITH_MAIL_FIXTURE")
    if fixture:
        return LocalMessageSource(Path(fixture))
    if os.environ.get("EDITH_MAIL_BACKEND", "").lower() == "gmail":
        from harness.integrations.google_auth import has_google_token

        # 토큰 없으면 brief가 RuntimeError로 깨지지 않게 local로 폴백.
        if has_google_token():
            return GmailMessageSource()
    return LocalMessageSource(edith_home / "raw" / "mail" / "messages.json")


# ── Priority classification rules (precedence 순서) ──

URGENT_KEYWORDS = ["긴급", "asap", "urgent", "오늘까지", "당일", "deadline", "시급"]
IMPORTANT_SUBJECT_KEYWORDS = ["회의", "미팅", "면접", "interview", "meeting", "review 요청"]
NEWSLETTER_SENDER_PATTERNS = ["noreply", "no-reply", "newsletter", "marketing"]
NEWSLETTER_LABELS = {"category_promotions", "INBOX/Newsletters", "Promotions"}
NOTIFICATION_SENDERS = ["github", "linkedin", "slack", "notion", "asana", "jira"]


def classify_priority(msg: Message) -> Priority:
    """precedence: urgent > important > newsletter > notification > normal."""
    body = (msg.subject + " " + msg.snippet).lower()
    sender = msg.sender.lower()

    if any(k in body for k in URGENT_KEYWORDS):
        return "urgent"
    if any(k in msg.subject.lower() for k in IMPORTANT_SUBJECT_KEYWORDS):
        return "important"
    if any(p in sender for p in NEWSLETTER_SENDER_PATTERNS):
        return "newsletter"
    if NEWSLETTER_LABELS.intersection(msg.labels):
        return "newsletter"
    if any(p in sender for p in NOTIFICATION_SENDERS):
        return "notification"
    return "normal"


@dataclass
class TriageItem:
    message: Message
    priority: Priority


def triage(messages: list[Message]) -> list[TriageItem]:
    return [TriageItem(message=m, priority=classify_priority(m)) for m in messages]


def render_triage(items: list[TriageItem], top_n: int = 10) -> str:
    if not items:
        return "─" * 50 + "\n읽지 않은 메일: 없음\n" + "─" * 50

    counts: Counter[Priority] = Counter(i.priority for i in items)
    lines = [
        "─" * 50,
        f"unread {len(items)}건 · "
        + " · ".join(f"{p}={counts[p]}" for p in PRIORITY_ORDER if counts[p]),
        "─" * 50,
    ]

    priority_rank: dict[Priority, int] = {p: i for i, p in enumerate(PRIORITY_ORDER)}
    sorted_items = sorted(
        items, key=lambda i: (priority_rank[i.priority], -i.message.received_at.timestamp())
    )
    for i in sorted_items[:top_n]:
        m = i.message
        marker = {
            "urgent": "❗",
            "important": "★",
            "notification": "·",
            "newsletter": "📰",
            "normal": " ",
        }[i.priority]
        lines.append(f"  {marker} [{i.priority}] {m.subject[:50]} — {m.sender[:30]}")
    if len(items) > top_n:
        lines.append(f"  ... +{len(items) - top_n}건")
    return "\n".join(lines)


def accuracy(items: list[TriageItem], expected: dict[str, Priority]) -> float:
    """test용 — message id → expected priority dict 와 비교."""
    if not items:
        return 1.0
    correct = sum(1 for i in items if expected.get(i.message.id) == i.priority)
    return correct / len(items)
