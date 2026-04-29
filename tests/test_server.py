"""PR #15 — harness/server.py FastAPI 진입점 테스트."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest

try:
    from fastapi.testclient import TestClient

    from harness.server import _verify_signature, make_app
except ImportError:
    pytest.skip("fastapi 또는 harness.server import 실패", allow_module_level=True)


SECRET = "test-secret-server"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """server make_app 의 auto-wire 가 사용자 .env 에 leak 되지 않게."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("RELAY_SECRET", raising=False)


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── _verify_signature ──────────────────────────────────────────────────


def test_verify_valid() -> None:
    body = b'{"q": "hi"}'
    assert _verify_signature(body, _sign(body), SECRET)


def test_verify_invalid() -> None:
    assert not _verify_signature(b"x", "sha256=" + "0" * 64, SECRET)


# ── /health ────────────────────────────────────────────────────────────


def test_health_basic(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["secret_configured"]
    assert data["telegram_configured"] is False


# ── /ask ───────────────────────────────────────────────────────────────


def _fake_run(task: str, edith_home: Path) -> Any:
    """trace-like 객체 mock."""

    class FakeTrace:
        id = "trace_test_001"
        output = f"echoed: {task}"
        n_steps = 1
        cost_tokens = 5

    return FakeTrace()


def test_ask_internal_no_signature_required(tmp_path: Path) -> None:
    """signature 헤더 없으면 내부망 호출로 간주, 통과."""
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post("/ask", json={"q": "안녕"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["answer"] == "echoed: 안녕"


def test_ask_with_valid_signature(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    body = json.dumps({"q": "hi"}).encode()
    resp = client.post(
        "/ask",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200


def test_ask_invalid_signature_rejected(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post(
        "/ask",
        json={"q": "hi"},
        headers={"X-Relay-Signature": "sha256=" + "0" * 64},
    )
    assert resp.status_code == 401


def test_ask_missing_question_rejected(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post("/ask", json={})
    assert resp.status_code == 400


def test_ask_runner_error_returns_500(tmp_path: Path) -> None:
    def boom(task: str, edith_home: Path) -> Any:
        raise RuntimeError("LLM API down")

    app = make_app(edith_home=tmp_path, secret=SECRET, runner=boom)
    client = TestClient(app)
    resp = client.post("/ask", json={"q": "x"})
    assert resp.status_code == 500
    assert resp.json()["ok"] is False


# ── /webhook/telegram ──────────────────────────────────────────────────


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def parse_update(self, payload: dict) -> Any:
        from harness.integrations.telegram import TelegramUpdate

        msg = payload.get("message", {})
        return TelegramUpdate(
            update_id=payload.get("update_id", 0),
            chat_id=msg.get("chat", {}).get("id", 0),
            text=msg.get("text", ""),
        )

    def send_message(self, chat_id: int, text: str, parse_mode: str | None = None) -> dict:
        self.sent.append((chat_id, text))
        return {"ok": True}


def test_telegram_webhook_runs_and_replies(tmp_path: Path) -> None:
    fake_tg = FakeTelegramClient()
    app = make_app(
        edith_home=tmp_path,
        secret=SECRET,
        runner=_fake_run,
        telegram_client=fake_tg,
    )
    client = TestClient(app)

    payload = {
        "update_id": 1,
        "message": {"chat": {"id": 8623533988}, "text": "오늘 일정"},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhook/telegram",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["answered"]
    # send_message 호출됐는지 확인
    assert len(fake_tg.sent) == 1
    chat_id, text = fake_tg.sent[0]
    assert chat_id == 8623533988
    assert "echoed: 오늘 일정" in text


def test_telegram_webhook_start_command(tmp_path: Path) -> None:
    fake_tg = FakeTelegramClient()
    app = make_app(
        edith_home=tmp_path,
        secret=SECRET,
        runner=_fake_run,
        telegram_client=fake_tg,
    )
    client = TestClient(app)

    payload = {
        "update_id": 1,
        "message": {"chat": {"id": 1}, "text": "/start"},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhook/telegram",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["command"] == "start"
    assert "안녕하세요" in fake_tg.sent[0][1]


def test_telegram_webhook_invalid_signature(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, telegram_client=FakeTelegramClient())
    client = TestClient(app)
    resp = client.post(
        "/webhook/telegram",
        json={"update_id": 1},
        headers={"X-Relay-Signature": "sha256=bad"},
    )
    assert resp.status_code == 401


def test_telegram_webhook_accepts_telegram_secret_token(tmp_path: Path) -> None:
    """Telegram 의 X-Telegram-Bot-Api-Secret-Token 헤더로 인증."""
    fake_tg = FakeTelegramClient()
    app = make_app(
        edith_home=tmp_path,
        secret=SECRET,
        runner=_fake_run,
        telegram_client=fake_tg,
    )
    client = TestClient(app)
    payload = {
        "update_id": 1,
        "message": {"chat": {"id": 1}, "text": "hi"},
    }
    resp = client.post(
        "/webhook/telegram",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert resp.status_code == 200
    assert resp.json()["answered"]


def test_telegram_webhook_wrong_telegram_token_rejected(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, telegram_client=FakeTelegramClient())
    client = TestClient(app)
    resp = client.post(
        "/webhook/telegram",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
    )
    assert resp.status_code == 401


def test_telegram_webhook_no_client_skips(tmp_path: Path) -> None:
    """telegram_client 미설정 → payload 받기만 하고 skip."""
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    body = json.dumps({"update_id": 1}).encode()
    resp = client.post(
        "/webhook/telegram",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert "telegram_client 미설정" in data["note"]


def test_telegram_webhook_runner_error_replies_to_user(tmp_path: Path) -> None:
    """runner 실패 시 사용자한테 에러 메시지 답장."""
    fake_tg = FakeTelegramClient()

    def boom(task: str, edith_home: Path) -> Any:
        raise RuntimeError("Grok rate limit")

    app = make_app(
        edith_home=tmp_path,
        secret=SECRET,
        runner=boom,
        telegram_client=fake_tg,
    )
    client = TestClient(app)

    payload = {"update_id": 1, "message": {"chat": {"id": 1}, "text": "hi"}}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhook/telegram",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 500
    # 사용자한테 오류 메시지 보냈는지
    assert len(fake_tg.sent) == 1
    assert "오류" in fake_tg.sent[0][1]
