"""Phase 3 F3 — Mail triage tests.

머지 기준: 50개 mock 메일 priority 정확도 ≥85%.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness.mail import (
    GmailMessageSource,
    LocalMessageSource,
    Message,
    Priority,
    accuracy,
    classify_priority,
    render_triage,
    triage,
)


def _msg(
    id_: str,
    sender: str = "x@y.com",
    subject: str = "",
    snippet: str = "",
    labels: list[str] | None = None,
    unread: bool = True,
) -> Message:
    return Message(
        id=id_,
        sender=sender,
        subject=subject,
        snippet=snippet,
        received_at=datetime.now(UTC),
        labels=labels or [],
        unread=unread,
    )


# ── classify_priority unit tests ──


def test_priority_urgent_keyword() -> None:
    m = _msg("1", subject="긴급: 오늘까지 컨펌 부탁드립니다", sender="boss@samil.com")
    assert classify_priority(m) == "urgent"


def test_priority_urgent_english() -> None:
    m = _msg("2", subject="URGENT: ASAP review needed", sender="x@y.com")
    assert classify_priority(m) == "urgent"


def test_priority_important_meeting() -> None:
    m = _msg("3", subject="회의 초청 — 주간 retro", sender="x@y.com")
    assert classify_priority(m) == "important"


def test_priority_important_interview() -> None:
    m = _msg("4", subject="Interview confirmation — Edith team", sender="hr@x.com")
    assert classify_priority(m) == "important"


def test_priority_newsletter_noreply() -> None:
    m = _msg("5", sender="noreply@medium.com", subject="Daily digest")
    assert classify_priority(m) == "newsletter"


def test_priority_newsletter_label() -> None:
    m = _msg("6", sender="x@x.com", labels=["category_promotions"])
    assert classify_priority(m) == "newsletter"


def test_priority_notification_github() -> None:
    m = _msg("7", sender="notifications@github.com", subject="PR review requested")
    # subject에 "review"는 있지만 important 키워드 아님; sender가 github → notification
    assert classify_priority(m) == "notification"


def test_priority_normal_default() -> None:
    m = _msg("8", sender="friend@x.com", subject="저녁 약속")
    assert classify_priority(m) == "normal"


def test_priority_precedence_urgent_over_meeting() -> None:
    """urgent 키워드가 회의 키워드보다 우선."""
    m = _msg("9", subject="긴급 회의 소집")
    assert classify_priority(m) == "urgent"


# ── 50-msg accuracy benchmark (머지 기준 ≥85%) ──


def _generate_50_msgs() -> tuple[list[Message], dict[str, Priority]]:
    msgs: list[Message] = []
    expected: dict[str, Priority] = {}

    # 10 urgent
    for i in range(10):
        m = _msg(f"u{i}", subject=f"긴급: 항목 {i} 컨펌 부탁", sender="boss@x.com")
        msgs.append(m)
        expected[m.id] = "urgent"

    # 10 important (meeting/interview)
    for i in range(10):
        m = _msg(f"i{i}", subject=f"회의 초청 — 항목 {i}", sender="pm@x.com")
        msgs.append(m)
        expected[m.id] = "important"

    # 10 notification (github/linkedin)
    for i in range(10):
        sender = "notifications@github.com" if i % 2 else "linkedin@linkedin.com"
        m = _msg(f"n{i}", sender=sender, subject=f"item {i}")
        msgs.append(m)
        expected[m.id] = "notification"

    # 15 newsletter (noreply/promotions)
    for i in range(15):
        if i % 3 == 0:
            m = _msg(f"nl{i}", sender="noreply@medium.com", subject=f"digest {i}")
        elif i % 3 == 1:
            m = _msg(f"nl{i}", sender="marketing@startup.com", subject=f"deal {i}")
        else:
            m = _msg(f"nl{i}", sender="x@y.com", labels=["category_promotions"])
        msgs.append(m)
        expected[m.id] = "newsletter"

    # 5 normal
    for i in range(5):
        m = _msg(f"x{i}", sender="friend@x.com", subject=f"잘 지내? {i}")
        msgs.append(m)
        expected[m.id] = "normal"

    return msgs, expected


def test_50_message_priority_accuracy_meets_threshold() -> None:
    """F3 머지 기준 — 50개 mock 메일 priority 정확도 ≥85%."""
    msgs, expected = _generate_50_msgs()
    items = triage(msgs)
    acc = accuracy(items, expected)
    misses = [
        (i.message.id, i.priority, expected[i.message.id])
        for i in items
        if expected[i.message.id] != i.priority
    ]
    assert acc >= 0.85, f"accuracy {acc:.2%}. misses: {misses}"


# ── LocalMessageSource ──


def test_local_source_empty_when_no_file(tmp_path: Path) -> None:
    src = LocalMessageSource(tmp_path / "missing.json")
    assert src.list_unread() == []


def test_local_source_filters_unread(tmp_path: Path) -> None:
    p = tmp_path / "msgs.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "sender": "a@b.com",
                    "subject": "unread",
                    "snippet": "...",
                    "received_at": datetime.now(UTC).isoformat(),
                    "labels": [],
                    "unread": True,
                },
                {
                    "id": "2",
                    "sender": "a@b.com",
                    "subject": "read",
                    "snippet": "...",
                    "received_at": datetime.now(UTC).isoformat(),
                    "labels": [],
                    "unread": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    msgs = LocalMessageSource(p).list_unread()
    assert len(msgs) == 1
    assert msgs[0].id == "1"


def test_local_source_sorts_newest_first(tmp_path: Path) -> None:
    p = tmp_path / "msgs.json"
    older = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    newer = datetime.now(UTC).isoformat()
    p.write_text(
        json.dumps(
            [
                {
                    "id": "old",
                    "sender": "x",
                    "subject": "",
                    "snippet": "",
                    "received_at": older,
                    "labels": [],
                    "unread": True,
                },
                {
                    "id": "new",
                    "sender": "x",
                    "subject": "",
                    "snippet": "",
                    "received_at": newer,
                    "labels": [],
                    "unread": True,
                },
            ]
        ),
        encoding="utf-8",
    )
    msgs = LocalMessageSource(p).list_unread()
    assert msgs[0].id == "new"
    assert msgs[1].id == "old"


def test_local_source_respects_limit(tmp_path: Path) -> None:
    p = tmp_path / "msgs.json"
    p.write_text(
        json.dumps(
            [
                {
                    "id": str(i),
                    "sender": "x",
                    "subject": "",
                    "snippet": "",
                    "received_at": datetime.now(UTC).isoformat(),
                    "labels": [],
                    "unread": True,
                }
                for i in range(10)
            ]
        ),
        encoding="utf-8",
    )
    msgs = LocalMessageSource(p).list_unread(limit=3)
    assert len(msgs) == 3


def test_local_source_handles_corrupt_json(tmp_path: Path) -> None:
    p = tmp_path / "msgs.json"
    p.write_text("{not json", encoding="utf-8")
    assert LocalMessageSource(p).list_unread() == []


# ── render ──


def test_render_triage_empty() -> None:
    text = render_triage([])
    assert "없음" in text


def test_render_triage_shows_counts() -> None:
    msgs, _ = _generate_50_msgs()
    items = triage(msgs)
    text = render_triage(items[:30], top_n=5)
    assert "unread 30건" in text
    assert "urgent" in text
    assert "+25건" in text  # truncation hint


# ── GmailMessageSource (미설정 시 안전 실패) ──


def test_gmail_message_source_raises_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 토큰·시크릿 경로를 빈 곳으로 → 실 호출 시 토큰 없어 RuntimeError(브라우저 flow X).
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "no_token.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", str(tmp_path / "no_secret.json"))
    src = GmailMessageSource()  # source 미주입 → lazy 실 호출
    with pytest.raises(RuntimeError):
        src.list_unread()
