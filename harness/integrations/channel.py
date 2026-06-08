"""Phase 4 F13 — 멀티채널 surface 추상화.

Edith의 입출력 표면(Telegram·Kakao·email·...)을 platform-agnostic Channel로 통일한다.
인터페이스를 추출해두면 새 채널은 어댑터 파일 하나로 끝난다.

OpenClaw처럼 14개 채널을 다 만들지 않는다: caller 없는 채널은 유지보수 부채.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from harness import policies
from harness.integrations.gmail import GmailSource
from harness.integrations.kakao import KakaoClient
from harness.integrations.os_notify import RunnerFn, send_notification
from harness.integrations.telegram import TelegramClient


def _assert_outbound_clean(text: str) -> None:
    """R5 (F24, PRD docs/08 §4.8). 모든 send 직전 단일 PII chokepoint.

    `policies.guard_outbound`를 호출해 외부로 나가는 텍스트에 PII가 있으면
    전송을 abort한다. 정상(PII 없는) 텍스트엔 영향이 없다 — 기존 send 동작 보존.
    MockChannel·TelegramChannel 두 구현이 공유해 중복을 막는다.
    """
    result = policies.guard_outbound(text)
    if not result["ok"]:
        raise RuntimeError(f"R5: PII in outbound — {result['reason']}")


@dataclass(frozen=True)
class IncomingMessage:
    """채널 무관 inbound 메시지."""

    channel: str  # "telegram" | "mock" | ...
    sender_id: str  # 채널 내 식별자 — chat_id, email addr 등
    text: str
    sender_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    # F21 — 이 메시지가 속한 scope. 분류 전 기본 personal (가장 보수적).
    # scope 휴리스틱(발신 도메인 등)은 후속; 지금은 per-item scope 필드만 마련.
    scope: str = "personal"

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")


class Channel(Protocol):
    """입출력 채널 interface — platform-agnostic.

    구현체:
    - TelegramChannel (실 환경)
    - KakaoChannel (실 환경, outbound-only self memo)
    - MockChannel (테스트)
    - EmailChannel (실 환경, outbound-only self notification)
    - OsNotifyChannel (macOS 로컬 알림)
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
        _assert_outbound_clean(text)  # R5 PII 게이트
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
        _assert_outbound_clean(text)  # R5 PII 게이트
        return self._client.send_message(chat_id=int(recipient), text=text)


class KakaoChannel:
    """KakaoTalk '나에게 보내기' 전용 outbound 채널.

    recipient는 인터페이스 호환용으로 받지만 무시한다. 일반 친구/채팅방 발송으로 확장하지
    않고, KakaoClient.send_memo(self memo endpoint)만 호출한다.
    """

    name = "kakao"

    def __init__(self, client: KakaoClient) -> None:
        self._client = client

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        return None

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        _assert_outbound_clean(text)  # R5 PII 게이트
        return self._client.send_memo(text)


class _EmailSender(Protocol):
    def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]: ...


class EmailChannel:
    """본인 주소로만 보내는 Gmail 알림 채널.

    recipient는 Kakao self memo처럼 인터페이스 호환용으로만 받고 무시한다. 임의 수신자
    발송은 approval-gated gmail_send executor 영역이므로 여기서는 EDITH_NOTIFY_EMAIL만 사용.
    """

    name = "email"

    def __init__(
        self,
        self_addr: str | None = None,
        sender: _EmailSender | None = None,
    ) -> None:
        env_addr = os.environ.get("EDITH_NOTIFY_EMAIL", "")
        self._self_addr = (self_addr if self_addr is not None else env_addr).strip()
        self._sender = sender

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        return None

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        _assert_outbound_clean(text)  # R5 PII 게이트
        if not self._self_addr:
            raise RuntimeError("EDITH_NOTIFY_EMAIL 없음 — 본인 알림 주소를 .env에 설정하세요.")
        sender = self._sender or GmailSource()
        return sender.send_message(to=self._self_addr, subject="☀️ Edith brief", body=text)


class OsNotifyChannel:
    """macOS 로컬 배너 알림 채널.

    recipient는 인터페이스 호환용으로 받지만 무시한다. 외부 발송은 아니지만 모든 Channel.send와
    동일하게 R5 PII 게이트를 적용한다.
    """

    name = "osnotify"

    def __init__(
        self,
        *,
        runner: RunnerFn | None = None,
        platform: str | None = None,
    ) -> None:
        self._runner = runner
        self._platform = platform

    def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage | None:
        return None

    def send(self, recipient: str, text: str) -> dict[str, Any]:
        _assert_outbound_clean(text)  # R5 PII 게이트
        return send_notification("Edith", text, runner=self._runner, platform=self._platform)


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
    "EmailChannel",
    "IncomingMessage",
    "KakaoChannel",
    "MockChannel",
    "OsNotifyChannel",
    "TelegramChannel",
]
