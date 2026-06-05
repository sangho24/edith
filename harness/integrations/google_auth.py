"""Google OAuth 공용 헬퍼 — Gmail + Calendar 단일 토큰.

Gmail(integrations/gmail.py)과 Calendar(calendar.py)가 **하나의 OAuth 토큰**을 공유한다.
`harness oauth google`가 통합 scope(gmail readonly+send, calendar readonly)로 동의 flow를
한 번 돌려 토큰을 저장하면, 두 소스 모두 그 토큰을 읽는다.

토큰·시크릿 위치(기본, 모두 secrets/ 아래 → .gitignore):
- client secret: GOOGLE_OAUTH_CLIENT_SECRETS_FILE 또는 <edith>/secrets/google_oauth.json
- token:         GOOGLE_TOKEN_FILE 또는 <edith>/secrets/google_token.json

google-auth-oauthlib·google-api-python-client는 optional 의존성([google]). 미설치면
실 호출 시점에만 RuntimeError(안내 메시지). 테스트는 service 주입으로 라이브러리 없이 검증.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 통합 scope — Google Cloud OAuth 동의화면에 등록된 것과 일치해야 함.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _edith_home() -> Path:
    return Path(os.environ.get("EDITH_HOME", str(Path.home() / "edith"))).resolve()


def default_secrets_file() -> Path:
    """다운로드한 OAuth client secret 경로."""
    env = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS_FILE")
    return Path(env) if env else _edith_home() / "secrets" / "google_oauth.json"


def default_token_file() -> Path:
    """저장된 OAuth 토큰 경로(첫 동의 후 생성)."""
    env = os.environ.get("GOOGLE_TOKEN_FILE")
    return Path(env) if env else _edith_home() / "secrets" / "google_token.json"


def load_google_credentials(
    secrets_file: Path | None = None,
    token_file: Path | None = None,
    scopes: list[str] | None = None,
    allow_flow: bool = True,
) -> Any:
    """토큰을 로드(필요 시 refresh). allow_flow=True면 토큰 없을 때 동의 flow 실행.

    google-auth-oauthlib·google-auth 필요. 미설치면 RuntimeError.
    """
    secrets_file = secrets_file or default_secrets_file()
    token_file = token_file or default_token_file()
    scopes = scopes or GOOGLE_SCOPES

    try:
        from google.auth.transport.requests import Request  # type: ignore[import-not-found]
        from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "Google API 클라이언트 필요 — uv pip install -e \".[google]\""
        ) from e

    creds: Any = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(token_file, creds)
        return creds

    if not allow_flow:
        raise RuntimeError(
            f"유효한 Google 토큰 없음: {token_file}. `harness oauth google` 먼저 실행."
        )
    if not secrets_file.exists():
        raise RuntimeError(
            f"OAuth client secret 없음: {secrets_file}. "
            "Google Cloud Console에서 OAuth 클라이언트(데스크톱) 만들고 JSON을 여기에 두세요."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes)
    creds = flow.run_local_server(port=0)
    _save_token(token_file, creds)
    return creds


def _save_token(token_file: Path, creds: Any) -> None:
    """토큰을 소유자 전용(0o600)으로 저장. OAuth access/refresh token이라 타 사용자 읽기 금지."""
    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        token_file.parent.chmod(0o700)
    except OSError:
        pass
    token_file.write_text(creds.to_json(), encoding="utf-8")
    try:
        token_file.chmod(0o600)
    except OSError:
        pass


def build_google_service(
    api: str,
    version: str,
    *,
    service: Any = None,
    scopes: list[str] | None = None,
    token_file: Path | None = None,
    secrets_file: Path | None = None,
    allow_flow: bool = False,
) -> Any:
    """googleapiclient service 빌드(또는 주입된 service 그대로 반환 — 테스트용).

    소스(GmailSource/GoogleCalendarSource)는 평소 allow_flow=False로 부르고(토큰 없으면
    실패), 토큰 생성은 `harness oauth google`(run_oauth_flow)에서만 한다.
    """
    if service is not None:
        return service
    creds = load_google_credentials(
        secrets_file=secrets_file,
        token_file=token_file,
        scopes=scopes,
        allow_flow=allow_flow,
    )
    try:
        from googleapiclient.discovery import build  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError('uv pip install -e ".[google]"') from e
    return build(api, version, credentials=creds, cache_discovery=False)


def run_oauth_flow(scopes: list[str] | None = None) -> dict[str, Any]:
    """동의 flow를 명시적으로 실행(브라우저)하고 토큰 저장. `harness oauth google`용."""
    token_file = default_token_file()
    creds = load_google_credentials(scopes=scopes or GOOGLE_SCOPES, allow_flow=True)
    return {
        "token_file": str(token_file),
        "scopes": list(getattr(creds, "scopes", scopes or GOOGLE_SCOPES) or []),
        "valid": bool(getattr(creds, "valid", False)),
    }


def token_status() -> dict[str, Any]:
    """저장된 토큰 상태(라이브러리 없이도 파일만 확인). `harness oauth google --status`용."""
    token_file = default_token_file()
    secrets_file = default_secrets_file()
    out: dict[str, Any] = {
        "token_file": str(token_file),
        "token_exists": token_file.exists(),
        "secrets_file": str(secrets_file),
        "secrets_exists": secrets_file.exists(),
        "scopes": [],
    }
    if token_file.exists():
        try:
            data = json.loads(token_file.read_text(encoding="utf-8"))
            out["scopes"] = data.get("scopes", [])
            out["client_email"] = data.get("account", "")
        except (json.JSONDecodeError, OSError):
            out["scopes"] = []
    return out


def has_google_token() -> bool:
    """유효성까지는 아니고 토큰 파일 존재 여부(소스 backend 자동 선택용)."""
    return default_token_file().exists()


__all__ = [
    "GOOGLE_SCOPES",
    "build_google_service",
    "default_secrets_file",
    "default_token_file",
    "has_google_token",
    "load_google_credentials",
    "run_oauth_flow",
    "token_status",
]
