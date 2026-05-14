"""Phase 4 F13 — 멀티채널 Channel 인터페이스 테스트.

핵심: 채널별 송수신 round-trip — payload → parse_incoming → IncomingMessage →
send → 채널 API 호출. Telegram·Mock 두 구현체가 같은 인터페이스를 만족하는지.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.integrations.channel import (
    ChannelRegistry,
    IncomingMessage,
    MockChannel,
    TelegramChannel,
)
from harness.integrations.telegram import TelegramClient


def _telegram_payload(chat_id: int = 123, text: str = "안녕") -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
            "from": {"first_name": "상호"},
        },
    }


# ── MockChannel ──────────────────────────────────────────────────────────


def test_mock_channel_round_trip() -> None:
    ch = MockChannel()
    msg = ch.parse_incoming({"sender_id": "u1", "text": "hi"})
    assert msg is not None
    assert msg.channel == "mock"
    assert msg.sender_id == "u1"
    assert msg.text == "hi"

    ch.send(msg.sender_id, "응답")
    assert ch.sent == [("u1", "응답")]


def test_mock_channel_drops_empty_payload() -> None:
    ch = MockChannel()
    assert ch.parse_incoming({"sender_id": "u1"}) is None
    assert ch.parse_incoming({"text": "hi"}) is None
    assert ch.parse_incoming({"sender_id": "u1", "text": ""}) is None


# ── TelegramChannel ──────────────────────────────────────────────────────


def test_telegram_channel_round_trip() -> None:
    posted: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
        posted.append((url, body))
        return {"ok": True}

    client = TelegramClient(token="t", http_post=fake_post)
    ch = TelegramChannel(client)

    msg = ch.parse_incoming(_telegram_payload(chat_id=999, text="오늘 일정"))
    assert msg is not None
    assert msg.channel == "telegram"
    assert msg.sender_id == "999"
    assert msg.text == "오늘 일정"
    assert msg.sender_name == "상호"

    ch.send(msg.sender_id, "일정 3건입니다")
    assert len(posted) == 1
    assert posted[0][1]["chat_id"] == 999
    assert posted[0][1]["text"] == "일정 3건입니다"


def test_telegram_channel_drops_non_message_payload() -> None:
    client = TelegramClient(token="t", http_post=lambda u, b: {"ok": True})
    ch = TelegramChannel(client)
    assert ch.parse_incoming({"update_id": 1, "callback_query": {}}) is None


def test_telegram_channel_respects_allowed_chat_ids() -> None:
    client = TelegramClient(
        token="t", allowed_chat_ids={111}, http_post=lambda u, b: {"ok": True}
    )
    ch = TelegramChannel(client)
    assert ch.parse_incoming(_telegram_payload(chat_id=111)) is not None
    assert ch.parse_incoming(_telegram_payload(chat_id=222)) is None


# ── ChannelRegistry ──────────────────────────────────────────────────────


def test_registry_register_and_get() -> None:
    reg = ChannelRegistry()
    mock = MockChannel()
    reg.register(mock)
    assert reg.get("mock") is mock
    assert reg.names() == ["mock"]


def test_registry_rejects_duplicate() -> None:
    reg = ChannelRegistry()
    reg.register(MockChannel())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(MockChannel())


def test_registry_unknown_channel_raises() -> None:
    reg = ChannelRegistry()
    with pytest.raises(KeyError, match="unknown channel"):
        reg.get("nope")


def test_incoming_message_is_command() -> None:
    assert IncomingMessage(channel="mock", sender_id="u", text="/help").is_command
    assert not IncomingMessage(channel="mock", sender_id="u", text="hi").is_command
