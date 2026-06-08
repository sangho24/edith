"""D1 — KakaoTalk self memo push integration."""

from __future__ import annotations

import json
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from harness.integrations.channel import KakaoChannel
from harness.integrations.kakao import (
    KAKAO_MEMO_SEND_URL,
    KAKAO_TEXT_MAX,
    KAKAO_TOKEN_URL,
    KakaoClient,
    format_kakao_brief_summary,
    has_kakao_token,
    kakao_token_status,
)


@dataclass
class BriefLike:
    today_str: str = "2026-06-08 (Mon)"
    top3: list[str] = field(
        default_factory=lambda: [
            "📧 urgent: 교수님 답장",
            "📅 10:00 미팅",
            "📰 ds-digest 확인",
        ]
    )
    today: dict[str, Any] = field(default_factory=lambda: {"n_events": 2})
    mail_summary: dict[str, Any] = field(default_factory=lambda: {"n_unread": 5})


def _write_token(path: Path, token: dict[str, Any] | None = None) -> None:
    data = token or {"access_token": "old-access", "refresh_token": "refresh"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _template_text(body: dict[str, str]) -> str:
    template = json.loads(body["template_object"])
    return str(template["text"])


def test_send_memo_posts_self_memo_template(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    _write_token(token_file, {"access_token": "access-token", "refresh_token": "refresh"})
    captured: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        captured.append((url, headers, body))
        return {"result_code": 0}

    client = KakaoClient(token_file=token_file, gui_url="http://edith.local", http_post=fake_post)
    response = client.send_memo("오늘 brief")

    assert response["result_code"] == 0
    assert len(captured) == 1
    url, headers, body = captured[0]
    assert url == KAKAO_MEMO_SEND_URL
    assert headers["Authorization"] == "Bearer access-token"
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    template = json.loads(body["template_object"])
    assert template == {
        "object_type": "text",
        "text": "오늘 brief",
        "link": {
            "web_url": "http://edith.local",
            "mobile_web_url": "http://edith.local",
        },
    }


def test_send_memo_truncates_text_to_kakao_limit(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    _write_token(token_file)
    captured: list[dict[str, str]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        captured.append(body)
        return {"result_code": 0}

    client = KakaoClient(token_file=token_file, http_post=fake_post)
    client.send_memo("x" * (KAKAO_TEXT_MAX + 50))

    sent = _template_text(captured[0])
    assert len(sent) == KAKAO_TEXT_MAX
    assert sent.endswith("…")


def test_send_memo_refreshes_on_401_and_retries(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    _write_token(token_file, {"access_token": "expired", "refresh_token": "refresh-token"})
    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        calls.append((url, headers, body))
        if url == KAKAO_MEMO_SEND_URL and headers["Authorization"] == "Bearer expired":
            return {"ok": False, "error_code": 401, "description": "expired"}
        if url == KAKAO_TOKEN_URL:
            assert body["grant_type"] == "refresh_token"
            assert body["client_id"] == "rest-key"
            assert body["refresh_token"] == "refresh-token"
            return {"access_token": "fresh", "expires_in": 3600}
        if url == KAKAO_MEMO_SEND_URL and headers["Authorization"] == "Bearer fresh":
            return {"result_code": 0}
        raise AssertionError("unexpected call")

    client = KakaoClient(
        rest_api_key="rest-key",
        token_file=token_file,
        http_post=fake_post,
    )
    assert client.send_memo("다시 전송") == {"result_code": 0}

    assert [c[0] for c in calls] == [KAKAO_MEMO_SEND_URL, KAKAO_TOKEN_URL, KAKAO_MEMO_SEND_URL]
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["access_token"] == "fresh"
    assert saved["refresh_token"] == "refresh-token"
    assert isinstance(saved["expires_at"], int)
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_send_memo_without_token_fails_safely(tmp_path: Path) -> None:
    client = KakaoClient(token_file=tmp_path / "missing.json")
    with pytest.raises(RuntimeError, match="Kakao 토큰 없음"):
        client.send_memo("hello")


def test_kakao_channel_send_passes_clean_text(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    _write_token(token_file)
    posted: list[str] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        posted.append(_template_text(body))
        return {"result_code": 0}

    ch = KakaoChannel(KakaoClient(token_file=token_file, http_post=fake_post))
    assert ch.parse_incoming({"anything": "ignored"}) is None
    assert ch.send("ignored-recipient", "일정 알림입니다") == {"result_code": 0}
    assert posted == ["일정 알림입니다"]


def test_kakao_channel_send_blocks_pii_before_post(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    _write_token(token_file)
    posted: list[dict[str, str]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        posted.append(body)
        return {"result_code": 0}

    ch = KakaoChannel(KakaoClient(token_file=token_file, http_post=fake_post))
    with pytest.raises(RuntimeError, match="R5: PII in outbound"):
        ch.send("self", "메일 leak@example.com 노출")
    assert posted == []


def test_format_kakao_brief_summary_top3_counts_and_limit() -> None:
    brief = BriefLike(top3=["긴 항목 " + "x" * 100, "두 번째", "세 번째", "네 번째"])
    text = format_kakao_brief_summary(brief, gui_url="http://127.0.0.1:8765")

    assert len(text) <= KAKAO_TEXT_MAX
    assert "2026-06-08" in text
    assert "Top 3" in text
    assert "1. 긴 항목" in text
    assert "2. 두 번째" in text
    assert "3. 세 번째" in text
    assert "네 번째" not in text
    assert "일정 2건 · 안읽음 5건" in text


def test_kakao_token_status_and_has_token(tmp_path: Path) -> None:
    token_file = tmp_path / "secrets" / "kakao_token.json"
    assert has_kakao_token(token_file) is False

    _write_token(
        token_file,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": int(time.time()) - 10,
        },
    )

    status = kakao_token_status(token_file)
    assert has_kakao_token(token_file) is True
    assert status["token_exists"] is True
    assert status["has_access_token"] is True
    assert status["has_refresh_token"] is True
    assert status["expired"] is True
