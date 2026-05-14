"""Phase 4 F13 — 멀티채널 surface 추상화.

Edith의 입출력 표면(Telegram·email·...)을 platform-agnostic Channel로 통일한다.
지금 실제 wired된 채널은 Telegram 하나뿐 — 인터페이스를 추출해두면 새 채널은
어댑터 파일 하나로 끝난다.

OpenClaw처럼 14개 채널을 다 만들지 않는다: caller 없는 채널은 유지보수 부채.
EmailChannel·KakaoChannel은 실제 호출부가 생길 때 어댑터를 추가한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from harness.integrations.telegram import TelegramClient


@dataclass(frozen=True)
class IncomingMessage:
    """채널 무관 inbound 메시지."""

    channel: str  # "telegram" | "mock" | ...
    sender_id: str  # 채널 내 식별자 — chat_id, email addr 등
    text: str
    sender_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")


class Channel(Protocol):
    """입출력 채널 interface — platform-agnostic.

    구현체:
    - TelegramChannel (실 환경)
    - MockChannel (테스트)
    - 추후: EmailChannel, KakaoChannel — 실제 호출부가 생기면 어댑터 추가
    """

    name: str

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """webhook/poll payload → IncomingMessage. 무시할 payload면 None."""
        ...

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        """recipient에게 text 전송. 반환은 채널 API 응답."""
        ...


class MockChannel:
    """테스트용 — send 호출을 기록, parse_incoming은 payload를 그대로 해석."""

    name = "mock"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        text = payload.get("text")
        sender = payload.get("sender_id")
        if not isinstance(text, str) or not text or sender is None:
            return None
        return IncomingMessage(
            channel=self.name,
            sender_id=str(sender),
            text=text,
            raw=payload,
        )

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        self.sent.append((recipient, text))
        return {"ok": True, "recipient": recipient}


class TelegramChannel:
    """TelegramClient를 Channel 인터페이스로 감싼 어댑터.

    parse_update / send_message의 Telegram 고유 타입을 channel-agnostic
    IncomingMessage / (recipient, text)로 변환한다.
    """

    name = "telegram"

    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        update = self._client.parse_update(payload)
        if update is None:
            return None
        return IncomingMessage(
            channel=self.name,
            sender_id=str(update.chat_id),
            text=update.text,
            sender_name=update.user_first_name,
            raw=payload,
        )

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        return self._client.send_message(chat_id=int(recipient), text=text)


class ChannelRegistry:
    """name → Channel. 멀티채널 dispatch의 진입점."""

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        if channel.name in self._channels:
            raise ValueError(f"channel {channel.name} already registered")
        self._channels[channel.name] = channel

    def get(self, name: str) -> Channel:
        if name not in self._channels:
            raise KeyError(f"unknown channel: {name}")
        return self._channels[name]

    def names(self) -> list[str]:
        return sorted(self._channels)


__all__ = [
    "Channel",
    "ChannelRegistry",
    "IncomingMessage",
    "MockChannel",
    "TelegramChannel",
]
