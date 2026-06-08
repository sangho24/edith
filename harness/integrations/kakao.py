"""KakaoTalk self memo push integration.

카카오 "나에게 보내기" 전용 클라이언트. 제3자 발송 API는 다루지 않는다.
테스트는 http_post 주입으로 hermetic 하게 검증하고, 실제 호출은 urllib만 사용한다.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

KAKAO_TEXT_MAX = 200
KAKAO_MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
DEFAULT_GUI_URL = "http://127.0.0.1:8765"

# signature: (url, headers, form_body) -> dict
HttpPostFn = Callable[[str, dict[str, str], dict[str, str]], dict[str, Any]]


def _edith_home() -> Path:
    return Path(os.environ.get("EDITH_HOME", str(Path.home() / "edith"))).resolve()


def default_token_file() -> Path:
    env = os.environ.get("KAKAO_TOKEN_FILE")
    return Path(env) if env else _edith_home() / "secrets" / "kakao_token.json"


def _save_token(token_file: Path, token: dict[str, Any]) -> None:
    """OAuth token을 소유자 전용(0o600)으로 저장."""
    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        token_file.parent.chmod(0o700)
    except OSError:
        pass
    token_file.write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        token_file.chmod(0o600)
    except OSError:
        pass


def _load_token(token_file: Path) -> dict[str, Any] | None:
    if not token_file.exists():
        return None
    try:
        data = json.loads(token_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _with_expiry(token: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    """Kakao refresh 응답의 expires_in을 저장 가능한 expires_at으로 정규화."""
    out = dict(token)
    if "expires_in" in out:
        try:
            out["expires_at"] = int(
                (now if now is not None else time.time()) + int(out["expires_in"])
            )
        except (TypeError, ValueError):
            pass
    if "refresh_token_expires_in" in out:
        try:
            out["refresh_token_expires_at"] = int(
                (now if now is not None else time.time()) + int(out["refresh_token_expires_in"])
            )
        except (TypeError, ValueError):
            pass
    return out


def _truncate(text: str, limit: int = KAKAO_TEXT_MAX) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[:limit]
    return text[: limit - 1] + "…"


def format_kakao_brief_summary(
    brief: Any,
    *,
    gui_url: str | None = None,
    limit: int = KAKAO_TEXT_MAX,
) -> str:
    """MorningBrief-like 객체를 Kakao text template 제한 안의 요약으로 변환."""
    today_str = str(getattr(brief, "today_str", "")).strip()
    top3 = list(getattr(brief, "top3", []) or [])[:3]
    today = getattr(brief, "today", {}) or {}
    mail_summary = getattr(brief, "mail_summary", {}) or {}

    n_events = int(today.get("n_events") or 0)
    n_unread = int(mail_summary.get("n_unread") or 0)

    lines = [f"☀️ Edith · {today_str}" if today_str else "☀️ Edith brief"]
    if top3:
        lines.append("Top 3")
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(top3, start=1))
    else:
        lines.append("Top 3 없음")
    lines.append(f"일정 {n_events}건 · 안읽음 {n_unread}건")
    lines.append(f"전체 brief: {gui_url or DEFAULT_GUI_URL}")
    return _truncate("\n".join(lines), limit)


def _real_http_post(
    url: str,
    headers: dict[str, str],
    body: dict[str, str],
) -> dict[str, Any]:
    """실제 HTTP POST. application/x-www-form-urlencoded, timeout 10s."""
    import urllib.error
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "error_code": e.code,
            "description": e.read().decode("utf-8", errors="replace"),
        }
    except urllib.error.URLError as e:
        return {"ok": False, "error_code": None, "description": str(e.reason)}


class KakaoClient:
    """KakaoTalk self memo API client.

    access/refresh token은 secrets/kakao_token.json에 저장한다. 토큰 발급 OAuth flow는
    아직 수동 절차로 남겨두고, 이 클라이언트는 저장된 토큰 로드와 refresh만 담당한다.
    """

    def __init__(
        self,
        *,
        rest_api_key: str | None = None,
        token_file: Path | None = None,
        gui_url: str | None = None,
        http_post: HttpPostFn | None = None,
    ) -> None:
        self.rest_api_key = (
            rest_api_key if rest_api_key is not None else os.environ.get("KAKAO_REST_API_KEY", "")
        )
        self.token_file = token_file or default_token_file()
        self.gui_url = gui_url or os.environ.get("EDITH_GUI_URL", DEFAULT_GUI_URL)
        self._http_post = http_post or _real_http_post

    def _token_or_raise(self) -> dict[str, Any]:
        token = _load_token(self.token_file)
        if not token or not token.get("access_token"):
            raise RuntimeError(
                f"Kakao 토큰 없음: {self.token_file}. `harness oauth kakao` 안내에 따라 "
                "secrets/kakao_token.json을 먼저 저장하세요."
            )
        return token

    def _memo_body(self, text: str) -> dict[str, str]:
        clipped = _truncate(text, KAKAO_TEXT_MAX)
        template = {
            "object_type": "text",
            "text": clipped,
            "link": {
                "web_url": self.gui_url,
                "mobile_web_url": self.gui_url,
            },
        }
        return {"template_object": json.dumps(template, ensure_ascii=False, separators=(",", ":"))}

    def refresh_access_token(self) -> dict[str, Any]:
        token = _load_token(self.token_file)
        if not token or not token.get("refresh_token"):
            raise RuntimeError(
                f"Kakao refresh_token 없음: {self.token_file}. `harness oauth kakao`로 "
                "토큰을 다시 준비하세요."
            )
        if not self.rest_api_key:
            raise RuntimeError("KAKAO_REST_API_KEY 없음. .env에 카카오 REST API 키를 추가하세요.")

        response = self._http_post(
            KAKAO_TOKEN_URL,
            {"Content-Type": "application/x-www-form-urlencoded"},
            {
                "grant_type": "refresh_token",
                "client_id": self.rest_api_key,
                "refresh_token": str(token["refresh_token"]),
            },
        )
        if response.get("ok") is False or not response.get("access_token"):
            raise RuntimeError(f"Kakao token refresh 실패: {response}")

        merged = dict(token)
        merged.update(_with_expiry(response))
        _save_token(self.token_file, merged)
        return merged

    def send_memo(self, text: str) -> dict[str, Any]:
        """KakaoTalk 나에게 보내기. 401이면 refresh 후 1회 재시도."""
        token = self._token_or_raise()

        def post(access_token: str) -> dict[str, Any]:
            return self._http_post(
                KAKAO_MEMO_SEND_URL,
                {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                self._memo_body(text),
            )

        response = post(str(token["access_token"]))
        if response.get("error_code") == 401:
            refreshed = self.refresh_access_token()
            response = post(str(refreshed["access_token"]))
        return response


def kakao_token_status(token_file: Path | None = None) -> dict[str, Any]:
    token_path = token_file or default_token_file()
    token = _load_token(token_path)
    expires_at = token.get("expires_at") if token else None
    expired = None
    if isinstance(expires_at, (int, float)):
        expired = expires_at <= time.time()
    return {
        "token_file": str(token_path),
        "token_exists": token_path.exists(),
        "has_access_token": bool(token and token.get("access_token")),
        "has_refresh_token": bool(token and token.get("refresh_token")),
        "expires_at": expires_at,
        "expired": expired,
        "rest_api_key_exists": bool(os.environ.get("KAKAO_REST_API_KEY", "").strip()),
    }


def has_kakao_token(token_file: Path | None = None) -> bool:
    token = _load_token(token_file or default_token_file())
    return bool(token and token.get("access_token"))


def run_oauth_flow_stub() -> dict[str, Any]:
    """브라우저 OAuth 자동 flow는 아직 미구현. 수동 발급 절차를 안내한다."""
    return {
        "ok": False,
        "message": (
            "카카오 OAuth 자동 동의 flow는 아직 준비 중입니다. docs/11_kakao_setup.md에 따라 "
            "access_token/refresh_token을 발급해 secrets/kakao_token.json에 저장하세요."
        ),
        "token_file": str(default_token_file()),
    }


__all__ = [
    "DEFAULT_GUI_URL",
    "KAKAO_MEMO_SEND_URL",
    "KAKAO_TEXT_MAX",
    "KAKAO_TOKEN_URL",
    "KakaoClient",
    "default_token_file",
    "format_kakao_brief_summary",
    "has_kakao_token",
    "kakao_token_status",
    "run_oauth_flow_stub",
]
