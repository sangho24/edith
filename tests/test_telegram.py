"""PR #15 — TelegramClient + parse_update 테스트.

실제 HTTP 호출 없이 inject 가능한 http_post mock 으로 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.integrations.telegram import TelegramClient, TelegramUpdate, _real_http_post

# ── parse_update ────────────────────────────────────────────────────────


def test_parse_update_message() -> None:
    client = TelegramClient(token="t")
    payload = {
        "update_id": 100,
        "message": {
            "chat": {"id": 8623533988, "type": "private"},
            "text": "hi",
            "from": {"first_name": "상호"},
        },
    }
    upd = client.parse_update(payload)
    assert upd is not None
    assert upd.update_id == 100
    assert upd.chat_id == 8623533988
    assert upd.text == "hi"
    assert upd.user_first_name == "상호"
    assert not upd.is_command


def test_parse_update_command_detected() -> None:
    client = TelegramClient(token="t")
    payload = {
        "update_id": 1,
        "message": {"chat": {"id": 1}, "text": "/start"},
    }
    upd = client.parse_update(payload)
    assert upd is not None
    assert upd.is_command


def test_parse_update_no_message_returns_none() -> None:
    client = TelegramClient(token="t")
    # callback_query 등은 처리 안 함
    payload = {"update_id": 5, "callback_query": {"data": "x"}}
    assert client.parse_update(payload) is None


def test_parse_update_missing_update_id_returns_none() -> None:
    client = TelegramClient(token="t")
    payload = {"message": {"chat": {"id": 1}, "text": "x"}}
    assert client.parse_update(payload) is None


def test_parse_update_filter_by_allowed_chat_ids() -> None:
    client = TelegramClient(token="t", allowed_chat_ids={1234})
    # 다른 chat → drop
    payload_other = {
        "update_id": 1,
        "message": {"chat": {"id": 5678}, "text": "hi"},
    }
    assert client.parse_update(payload_other) is None

    # 허용된 chat → 통과
    payload_ok = {
        "update_id": 2,
        "message": {"chat": {"id": 1234}, "text": "hi"},
    }
    upd = client.parse_update(payload_ok)
    assert upd is not None
    assert upd.chat_id == 1234


def test_parse_update_edited_message() -> None:
    client = TelegramClient(token="t")
    payload = {
        "update_id": 1,
        "edited_message": {"chat": {"id": 1}, "text": "edited"},
    }
    upd = client.parse_update(payload)
    assert upd is not None
    assert upd.text == "edited"


def test_parse_update_text_not_str_returns_none() -> None:
    """photo 만 있는 메시지처럼 text 없으면 drop."""
    client = TelegramClient(token="t")
    payload = {"update_id": 1, "message": {"chat": {"id": 1}}}
    assert client.parse_update(payload) is None


# ── send_message ────────────────────────────────────────────────────────


def test_send_message_calls_correct_url_and_body() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
        captured.append((url, body))
        return {"ok": True, "result": {"message_id": 42}}

    client = TelegramClient(token="testtoken", http_post=fake_post)
    resp = client.send_message(chat_id=999, text="hello")
    assert resp["ok"]
    assert len(captured) == 1
    url, body = captured[0]
    assert url == "https://api.telegram.org/bottesttoken/sendMessage"
    assert body["chat_id"] == 999
    assert body["text"] == "hello"


def test_send_message_truncates_to_4096() -> None:
    captured: list[dict[str, Any]] = []
    client = TelegramClient(
        token="t", http_post=lambda u, b: (captured.append(b), {"ok": True})[1]
    )
    long = "x" * 5000
    client.send_message(chat_id=1, text=long)
    assert len(captured[0]["text"]) == 4096


def test_send_message_with_parse_mode() -> None:
    captured: list[dict[str, Any]] = []
    client = TelegramClient(
        token="t", http_post=lambda u, b: (captured.append(b), {"ok": True})[1]
    )
    client.send_message(chat_id=1, text="**bold**", parse_mode="MarkdownV2")
    assert captured[0]["parse_mode"] == "MarkdownV2"


# ── set_webhook / delete_webhook ────────────────────────────────────────


def test_set_webhook() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []
    client = TelegramClient(
        token="t",
        http_post=lambda u, b: (captured.append((u, b)), {"ok": True})[1],
    )
    client.set_webhook(url="https://relay.example.com/webhook/telegram", secret_token="s")
    url, body = captured[0]
    assert url.endswith("/setWebhook")
    assert body["url"] == "https://relay.example.com/webhook/telegram"
    assert body["secret_token"] == "s"


def test_delete_webhook() -> None:
    captured: list[tuple[str, dict[str, Any]]] = []
    client = TelegramClient(
        token="t",
        http_post=lambda u, b: (captured.append((u, b)), {"ok": True})[1],
    )
    client.delete_webhook()
    assert captured[0][0].endswith("/deleteWebhook")


# ── 초기화 검증 ──────────────────────────────────────────────────────────


def test_empty_token_raises() -> None:
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramClient(token="")


# ── _real_http_post 의 시그니처는 testable (실제 네트워크 X) ────────────


def test_real_http_post_signature() -> None:
    """타입 시그니처만 검증 — 실제 호출 X."""
    assert callable(_real_http_post)
    # callable 이고, 실제 네트워크 호출은 e2e 환경에서만.


# ── Dataclass 기본값 ────────────────────────────────────────────────────


def test_telegram_update_dataclass() -> None:
    u = TelegramUpdate(update_id=1, chat_id=2, text="hi")
    assert u.user_first_name == ""
    assert not u.is_command
