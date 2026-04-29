"""PR #15 — Telegram Bot API integration.

핸드폰 ↔ Edith 양방향 채널.

핵심:
- TelegramClient: send / parse_update (외부 호출 testable)
- 실제 HTTP 호출은 inject 가능한 http_post 로 모킹
- VPS relay 가 webhook 을 받으면 → TelegramClient.parse_update 로 chat_id/text 추출 →
  harness server (MacBook) 에 forward → 응답을 send_message 로 답신.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# inject 가능한 http_post (test 시 mock).
# signature: (url, json_body) -> dict
HttpPostFn = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class TelegramUpdate:
    """webhook payload 의 핵심만 추출."""

    update_id: int
    chat_id: int
    text: str
    user_first_name: str = ""

    @property
    def is_command(self) -> bool:
        return self.text.startswith("/")


def _real_http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    """실제 HTTP POST (기본). urllib 만 사용 — 외부 의존성 없음."""
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "error_code": e.code,
            "description": e.read().decode("utf-8", errors="replace"),
        }


class TelegramClient:
    """Telegram Bot API 클라이언트.

    예: client = TelegramClient(token=os.environ["TELEGRAM_BOT_TOKEN"])
        client.send_message(chat_id=..., text="hi")
    """

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        token: str,
        allowed_chat_ids: set[int] | None = None,
        http_post: HttpPostFn | None = None,
    ) -> None:
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN 필요")
        self.token = token
        self.allowed_chat_ids = allowed_chat_ids
        self._http_post = http_post or _real_http_post

    def _url(self, method: str) -> str:
        return self.BASE_URL.format(token=self.token, method=method)

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """sendMessage API.

        text 는 4096자 제한 — 넘으면 잘라서 전송.
        """
        body: dict[str, Any] = {"chat_id": chat_id, "text": text[:4096]}
        if parse_mode:
            body["parse_mode"] = parse_mode
        return self._http_post(self._url("sendMessage"), body)

    def parse_update(self, payload: dict[str, Any]) -> TelegramUpdate | None:
        """webhook payload → TelegramUpdate.

        message · edited_message · channel_post 만 처리. 그 외 (callback_query 등) None.
        allowed_chat_ids 설정돼있고 매치 안 하면 None (silent drop).
        """
        update_id = payload.get("update_id")
        if not isinstance(update_id, int):
            return None

        # message / edited_message / channel_post 중 하나
        for key in ("message", "edited_message", "channel_post"):
            msg = payload.get(key)
            if isinstance(msg, dict):
                break
        else:
            return None

        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        text = msg.get("text")
        if not isinstance(chat_id, int):
            return None
        if not isinstance(text, str) or not text:
            # text 없는 메시지 (사진·스티커·등) drop
            return None

        if self.allowed_chat_ids is not None and chat_id not in self.allowed_chat_ids:
            return None

        from_user = msg.get("from", {})
        first_name = from_user.get("first_name", "") if isinstance(from_user, dict) else ""

        return TelegramUpdate(
            update_id=update_id,
            chat_id=chat_id,
            text=text,
            user_first_name=first_name,
        )

    def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        """Telegram 에 webhook URL 등록. 운영 시 한 번만 호출."""
        body: dict[str, Any] = {"url": url}
        if secret_token:
            body["secret_token"] = secret_token
        return self._http_post(self._url("setWebhook"), body)

    def delete_webhook(self) -> dict[str, Any]:
        return self._http_post(self._url("deleteWebhook"), {})
