"""PR #14 — Gmail integration via Google OAuth + Gmail API.

흐름:
1. GOOGLE_OAUTH_CLIENT_SECRETS_FILE (다운로드한 client_secret.json) 사용
2. 첫 실행 시 InstalledAppFlow 가 브라우저 띄움 → OAuth 동의 → refresh_token 저장
3. 이후 token 자동 갱신, scopes 변경 시 재인증

상위 추상화:
- MailSource Protocol (mail_triage F3 가 이 인터페이스로 받음)
- GmailSource (real)
- MockMailSource (테스트)

scope 는 readonly · send · modify 셋만 사용. 외부 send 는 policies.allow() + approval 거침.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from harness.integrations.google_auth import GOOGLE_SCOPES, load_google_credentials

# Gmail은 Calendar와 단일 토큰을 공유한다(google_auth.GOOGLE_SCOPES). 최소 권한 —
# 읽기 + 발송만, modify(삭제·수정)는 요청하지 않는다. 별도 credential 로딩 경로를 두지 않음.
GMAIL_SCOPES = GOOGLE_SCOPES


@dataclass(frozen=True)
class MailMessage:
    """메일 메시지의 platform-agnostic 표현."""

    id: str
    thread_id: str
    sender: str
    subject: str
    snippet: str
    date: datetime
    labels: tuple[str, ...] = ()
    is_unread: bool = False

    @property
    def short_sender(self) -> str:
        """이름 부분만 추출 (예: 'Alice <alice@x.com>' → 'Alice')."""
        if "<" in self.sender:
            return self.sender.split("<", 1)[0].strip().strip('"')
        return self.sender


class MailSource(Protocol):
    """메일 source interface — F3 mail_triage 가 사용."""

    def list_unread(self, max_results: int = 20) -> list[MailMessage]: ...

    def get_thread(self, thread_id: str) -> list[MailMessage]: ...


class MockMailSource:
    """테스트용 — 미리 정의된 메시지 반환."""

    def __init__(self, messages: list[MailMessage] | None = None) -> None:
        self._messages = messages or []

    def list_unread(self, max_results: int = 20) -> list[MailMessage]:
        unread = [m for m in self._messages if m.is_unread]
        return unread[:max_results]

    def get_thread(self, thread_id: str) -> list[MailMessage]:
        return [m for m in self._messages if m.thread_id == thread_id]


class GmailSource:
    """실 Gmail API 호출.

    Lazy import — google-api-python-client 미설치 환경에선 import 만 안 됨.
    test 시 monkeypatch 또는 MockMailSource 로 대체.
    """

    def __init__(
        self,
        secrets_file: Path | None = None,
        token_file: Path | None = None,
        scopes: list[str] | None = None,
        service: Any = None,
    ) -> None:
        if service is not None:
            # 테스트 시 미리 만든 service 주입
            self._service = service
            return

        secrets_file = secrets_file or Path(
            os.environ.get(
                "GOOGLE_OAUTH_CLIENT_SECRETS_FILE",
                str(Path.home() / "edith" / "secrets" / "google_oauth.json"),
            )
        )
        token_file = token_file or Path(
            os.environ.get(
                "GOOGLE_TOKEN_FILE",
                str(Path.home() / "edith" / "secrets" / "google_token.json"),
            )
        )
        scopes = scopes or GMAIL_SCOPES

        # 읽기/발송 경로는 브라우저 flow를 절대 트리거하지 않는다(allow_flow=False).
        # 토큰 발급은 `harness oauth google`(run_oauth_flow)에서만.
        creds = load_google_credentials(
            secrets_file=secrets_file, token_file=token_file, scopes=scopes, allow_flow=False
        )
        try:
            from googleapiclient.discovery import build  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError('uv pip install -e ".[google]"') from e
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def list_unread(self, max_results: int = 20) -> list[MailMessage]:
        resp = (
            self._service.users()
            .messages()
            .list(userId="me", labelIds=["UNREAD", "INBOX"], maxResults=max_results)
            .execute()
        )
        msg_ids = [m["id"] for m in resp.get("messages", [])]
        return [self._fetch_message(mid) for mid in msg_ids]

    def get_thread(self, thread_id: str) -> list[MailMessage]:
        resp = self._service.users().threads().get(userId="me", id=thread_id).execute()
        return [self._parse(m) for m in resp.get("messages", [])]

    def send_message(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """메일 발송 (gmail.send scope 필요).

        외부 write — policies.allow()의 R2로 차단되고, request_approval +
        ApprovalExecutor를 거쳐야만 실행된다. 직접 호출 금지.
        """
        import base64
        from email.message import EmailMessage as _EmailMessage

        mime = _EmailMessage()
        mime["To"] = to
        mime["Subject"] = subject
        mime.set_content(body)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        return (
            self._service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )

    def _fetch_message(self, msg_id: str) -> MailMessage:
        m = (
            self._service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata")
            .execute()
        )
        return self._parse(m)

    def _parse(self, m: dict[str, Any]) -> MailMessage:
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        labels = tuple(m.get("labelIds", []))
        # Gmail internalDate 는 epoch ms. UTC-aware로 — fixture(aware)와 섞여 정렬돼도 안전.
        ts_ms = int(m.get("internalDate", 0))
        return MailMessage(
            id=m["id"],
            thread_id=m["threadId"],
            sender=headers.get("from", ""),
            subject=headers.get("subject", ""),
            snippet=m.get("snippet", ""),
            date=datetime.fromtimestamp(ts_ms / 1000, tz=UTC) if ts_ms else datetime.min,
            labels=labels,
            is_unread="UNREAD" in labels,
        )


def get_mail_source(
    fallback_to_mock: bool = True,
) -> MailSource:
    """env 기반 source factory.

    GOOGLE_OAUTH_CLIENT_SECRETS_FILE 가 존재하면 GmailSource, 아니면 Mock.
    """
    secrets_file = Path(
        os.environ.get(
            "GOOGLE_OAUTH_CLIENT_SECRETS_FILE",
            "",
        )
    )
    if secrets_file and secrets_file.exists():
        try:
            return GmailSource()
        except RuntimeError:
            if fallback_to_mock:
                return MockMailSource()
            raise
    if fallback_to_mock:
        return MockMailSource()
    raise RuntimeError("GOOGLE_OAUTH_CLIENT_SECRETS_FILE 없음 — mail source 없음")


__all__ = [
    "GMAIL_SCOPES",
    "MailMessage",
    "MailSource",
    "GmailSource",
    "MockMailSource",
    "get_mail_source",
]
