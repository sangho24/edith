"""PR #15 — harness/server.py FastAPI 진입점 테스트."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
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
    monkeypatch.delenv("EDITH_GUI_TOKEN", raising=False)


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


def test_gui_token_missing_logs_bind_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="harness.server"):
        make_app(edith_home=tmp_path, secret=SECRET)
    assert "⚠️ EDITH_GUI_TOKEN 미설정 — 127.0.0.1 바인드 권장" in caplog.text


def test_server_startup_missing_llm_logs_doctor_hint(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EDITH_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with caplog.at_level(logging.WARNING, logger="harness.server"):
        make_app(edith_home=tmp_path, secret=SECRET)

    assert "harness doctor" in caplog.text
    assert "EDITH_LLM" in caplog.text


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


def test_ask_without_gui_token_env_keeps_existing_behavior(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post("/ask", json={"q": "토큰 없이"})
    assert resp.status_code == 200


def test_gui_token_required_for_ask_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITH_GUI_TOKEN", "gui-secret")
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)

    assert client.post("/ask", json={"q": "hi"}).status_code == 401
    resp = client.post("/ask", json={"q": "hi"}, headers={"X-Edith-Token": "gui-secret"})
    assert resp.status_code == 200


def test_gui_token_required_for_ui_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITH_GUI_TOKEN", "gui-secret")
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)

    assert client.get("/ui/traces").status_code == 401
    resp = client.get("/ui/traces", headers={"X-Edith-Token": "gui-secret"})
    assert resp.status_code == 200


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


def test_ask_rejects_non_object_payload(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post("/ask", json=["not", "object"])
    assert resp.status_code == 400


def test_ask_rejects_non_string_question(tmp_path: Path) -> None:
    app = make_app(edith_home=tmp_path, secret=SECRET, runner=_fake_run)
    client = TestClient(app)
    resp = client.post("/ask", json={"q": 123})
    assert resp.status_code == 400


def test_ask_runner_error_returns_500(tmp_path: Path) -> None:
    def boom(task: str, edith_home: Path) -> Any:
        raise RuntimeError("LLM API down")

    app = make_app(edith_home=tmp_path, secret=SECRET, runner=boom)
    client = TestClient(app)
    resp = client.post("/ask", json={"q": "x"})
    assert resp.status_code == 500
    assert resp.json()["ok"] is False


def test_ask_missing_llm_config_returns_friendly_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EDITH_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = make_app(edith_home=tmp_path, secret=SECRET)
    client = TestClient(app)

    resp = client.post("/ask", json={"q": "안녕"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "harness doctor" in data["answer"]


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


def test_telegram_webhook_ignores_gui_token_and_uses_hmac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDITH_GUI_TOKEN", "gui-secret")
    fake_tg = FakeTelegramClient()
    app = make_app(
        edith_home=tmp_path,
        secret=SECRET,
        runner=_fake_run,
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
    assert resp.status_code == 200
    assert resp.json()["answered"]


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
    # /start 안내 → /help 가이드 포함
    assert "/help" in fake_tg.sent[0][1]


def test_telegram_webhook_help_command(tmp_path: Path) -> None:
    """/help 메시지에 17 tools 카테고리 다 보임."""
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
        "message": {"chat": {"id": 1}, "text": "/help"},
    }
    body = json.dumps(payload).encode()
    resp = client.post(
        "/webhook/telegram",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["command"] == "help"

    help_msg = fake_tg.sent[0][1]
    # 핵심 카테고리 모두 포함
    for keyword in ["일정", "메모", "wiki", "검색", "arxiv", "trace"]:
        assert keyword in help_msg, f"'{keyword}' missing in /help"
    # Telegram 4096 자 한도 내
    assert len(help_msg) < 4096


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


# ── PR #18 — _compose_answer fallback 로직 ──


def _make_trace(
    output: str | None = None,
    finalize_reason: str | None = None,
    events: list | None = None,
) -> Any:
    """fake Trace mock — minimal duck-typed object for _compose_answer."""
    from dataclasses import dataclass, field

    from harness.state import Event

    @dataclass
    class FakeTrace:
        output: str | None = None
        finalize_reason: str | None = None
        events: list[Event] = field(default_factory=list)

    return FakeTrace(
        output=output,
        finalize_reason=finalize_reason,
        events=[Event(t=evt[0], kind=evt[1], payload=evt[2]) for evt in (events or [])],
    )


def test_compose_answer_uses_output_if_present() -> None:
    from harness.server import _compose_answer

    trace = _make_trace(output="안녕하세요", finalize_reason="end_turn")
    assert _compose_answer(trace) == "안녕하세요"


def test_compose_answer_429_friendly_message() -> None:
    from harness.server import _compose_answer

    trace = _make_trace(
        output="",
        finalize_reason="error",
        events=[(0.0, "error", {"msg": "Error code: 429 - RESOURCE_EXHAUSTED ..."})],
    )
    out = _compose_answer(trace)
    assert "rate limit" in out
    assert "잠시 후" in out


def test_compose_answer_503_friendly_message() -> None:
    from harness.server import _compose_answer

    trace = _make_trace(
        output="",
        finalize_reason="error",
        events=[(0.0, "error", {"msg": "Error code: 503 - UNAVAILABLE"})],
    )
    out = _compose_answer(trace)
    assert "일시 불안정" in out


def test_compose_answer_summarizes_capture_text_action() -> None:
    """tool 호출 후 텍스트 출력 없는 Gemini empty completion 패턴."""
    from harness.server import _compose_answer

    trace = _make_trace(
        output="",
        finalize_reason="end_turn",
        events=[
            (0.0, "action", {"tool": "capture_text", "args": {"text": "x"}}),
            (0.5, "observation", {"tool": "capture_text", "result": "ok"}),
        ],
    )
    out = _compose_answer(trace)
    assert "메모" in out


def test_compose_answer_budget_friendly_message() -> None:
    from harness.server import _compose_answer

    trace = _make_trace(output="", finalize_reason="budget_steps")
    out = _compose_answer(trace)
    assert "예산" in out or "한도" in out


def test_compose_answer_fallback_when_nothing() -> None:
    from harness.server import _compose_answer

    trace = _make_trace(output="", finalize_reason=None)
    out = _compose_answer(trace)
    assert "응답" in out


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
