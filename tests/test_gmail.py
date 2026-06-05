"""PR #14 — Gmail integration tests.

google-api-python-client 미설치 환경에서도 Mock 부분은 검증 가능해야 함.
실제 GmailSource 는 service injection 으로 테스트.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness.integrations.gmail import (
    GMAIL_SCOPES,
    GmailSource,
    MailMessage,
    MockMailSource,
    get_mail_source,
)

# ── MailMessage ─────────────────────────────────────────────────────────


def test_short_sender_with_angle_brackets() -> None:
    m = MailMessage(
        id="1",
        thread_id="t",
        sender="Alice <alice@x.com>",
        subject="hi",
        snippet="",
        date=datetime(2026, 4, 29, 10, 0),
    )
    assert m.short_sender == "Alice"


def test_short_sender_with_quoted_name() -> None:
    m = MailMessage(
        id="1",
        thread_id="t",
        sender='"Bob Kim" <bob@x.com>',
        subject="x",
        snippet="",
        date=datetime.now(),
    )
    assert m.short_sender == "Bob Kim"


def test_short_sender_email_only() -> None:
    m = MailMessage(
        id="1",
        thread_id="t",
        sender="alice@x.com",
        subject="x",
        snippet="",
        date=datetime.now(),
    )
    assert m.short_sender == "alice@x.com"


# ── MockMailSource ──────────────────────────────────────────────────────


def _msg(
    id: str = "1",
    thread_id: str = "t1",
    is_unread: bool = True,
    sender: str = "x@y",
    subject: str = "s",
) -> MailMessage:
    return MailMessage(
        id=id,
        thread_id=thread_id,
        sender=sender,
        subject=subject,
        snippet="",
        date=datetime(2026, 4, 29, 10, 0),
        is_unread=is_unread,
    )


def test_mock_list_unread_filters_unread() -> None:
    src = MockMailSource(
        [
            _msg(id="1", is_unread=True),
            _msg(id="2", is_unread=False),
            _msg(id="3", is_unread=True),
        ]
    )
    out = src.list_unread()
    assert len(out) == 2
    assert {m.id for m in out} == {"1", "3"}


def test_mock_list_unread_max_results() -> None:
    src = MockMailSource([_msg(id=str(i), is_unread=True) for i in range(50)])
    out = src.list_unread(max_results=5)
    assert len(out) == 5


def test_mock_get_thread_filters_thread_id() -> None:
    src = MockMailSource(
        [
            _msg(id="1", thread_id="t1"),
            _msg(id="2", thread_id="t2"),
            _msg(id="3", thread_id="t1"),
        ]
    )
    out = src.get_thread("t1")
    assert {m.id for m in out} == {"1", "3"}


# ── GmailSource (service injected) ──────────────────────────────────────


def _fake_gmail_message(
    msg_id: str = "abc",
    thread_id: str = "thr1",
    from_: str = "alice@x.com",
    subject: str = "Hello",
    snippet: str = "preview",
    epoch_ms: int = 1714377600000,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Gmail API users.messages.get 응답 형식 mock."""
    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "internalDate": str(epoch_ms),
        "labelIds": labels or ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": from_},
                {"name": "Subject", "value": subject},
            ]
        },
    }


def _make_fake_service(messages_to_return: list[dict[str, Any]]) -> Any:
    """Gmail API service.users().messages().list/get chain 을 mock."""
    service = MagicMock()
    list_resp = {"messages": [{"id": m["id"]} for m in messages_to_return]}
    by_id = {m["id"]: m for m in messages_to_return}

    service.users.return_value.messages.return_value.list.return_value.execute.return_value = (
        list_resp
    )

    def get_side_effect(userId: str, id: str, format: str = "full") -> Any:
        m = MagicMock()
        m.execute.return_value = by_id[id]
        return m

    service.users.return_value.messages.return_value.get.side_effect = get_side_effect

    return service


def test_gmail_source_list_unread_with_injected_service() -> None:
    fake_msgs = [
        _fake_gmail_message(msg_id="m1", subject="안녕", from_="A <a@x.com>"),
        _fake_gmail_message(msg_id="m2", subject="회의", from_="B <b@x.com>"),
    ]
    service = _make_fake_service(fake_msgs)
    src = GmailSource(service=service)

    out = src.list_unread(max_results=10)
    assert len(out) == 2
    titles = {m.subject for m in out}
    assert titles == {"안녕", "회의"}
    assert all(m.is_unread for m in out)
    senders = {m.short_sender for m in out}
    assert senders == {"A", "B"}


def test_gmail_source_search_with_injected_service() -> None:
    # 읽음 상태 메일도 검색됨(list q= 경로). 비씨카드 결과 메일 시나리오.
    fake = _make_fake_service(
        [_fake_gmail_message(msg_id="m1", subject="[비씨카드] 채용 결과 안내", labels=["INBOX"])]
    )
    src = GmailSource(service=fake)
    out = src.search("비씨카드", max_results=5)
    assert len(out) == 1
    assert "비씨카드" in out[0].subject
    assert not out[0].is_unread  # 읽은 메일도 잡힘


def test_gmail_source_get_thread() -> None:
    service = MagicMock()
    service.users.return_value.threads.return_value.get.return_value.execute.return_value = {
        "messages": [
            _fake_gmail_message(msg_id="m1", thread_id="thrA"),
            _fake_gmail_message(msg_id="m2", thread_id="thrA"),
        ]
    }
    src = GmailSource(service=service)
    out = src.get_thread("thrA")
    assert len(out) == 2
    assert out[0].id == "m1"


def test_gmail_source_parse_internal_date() -> None:
    service = _make_fake_service(
        [_fake_gmail_message(msg_id="m1", epoch_ms=1714377600000)]
    )
    src = GmailSource(service=service)
    out = src.list_unread(1)
    # epoch_ms = 1714377600000 → 2024-04-29
    assert out[0].date.year == 2024
    assert out[0].date.tzinfo is not None  # UTC-aware — fixture(aware)와 섞여도 정렬 안전


def test_gmail_source_unread_label_detection() -> None:
    service = _make_fake_service(
        [
            _fake_gmail_message(msg_id="m1", labels=["INBOX", "UNREAD"]),
            _fake_gmail_message(msg_id="m2", labels=["INBOX"]),
        ]
    )
    src = GmailSource(service=service)
    out = src.list_unread(10)
    by_id = {m.id: m for m in out}
    assert by_id["m1"].is_unread
    assert not by_id["m2"].is_unread


# ── get_mail_source ─────────────────────────────────────────────────────


def test_get_source_fallback_to_mock_no_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """secrets 파일 없으면 Mock 으로 fallback."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", str(tmp_path / "no_such.json"))
    src = get_mail_source(fallback_to_mock=True)
    assert isinstance(src, MockMailSource)


def test_get_source_raise_no_secrets_no_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", str(tmp_path / "no.json"))
    with pytest.raises(RuntimeError):
        get_mail_source(fallback_to_mock=False)


# ── 상수 검증 ───────────────────────────────────────────────────────────


def test_gmail_scopes_minimal_unified() -> None:
    """Gmail+Calendar 단일 토큰의 최소 scope — modify(수정/삭제)는 요청하지 않는다."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in GMAIL_SCOPES
    assert "https://www.googleapis.com/auth/gmail.send" in GMAIL_SCOPES
    assert "https://www.googleapis.com/auth/calendar.readonly" in GMAIL_SCOPES
    assert "https://www.googleapis.com/auth/gmail.modify" not in GMAIL_SCOPES
