"""F16 — Web GUI + /brief 명령 테스트."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

try:
    from fastapi.testclient import TestClient

    from harness.server import make_app
except ImportError:
    pytest.skip("fastapi 또는 harness.server import 실패", allow_module_level=True)

SECRET = "test-secret-webui"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("RELAY_SECRET", raising=False)
    monkeypatch.delenv("EDITH_CALENDAR_FIXTURE", raising=False)
    monkeypatch.delenv("EDITH_MAIL_FIXTURE", raising=False)
    monkeypatch.delenv("EDITH_DS_DIGEST_LATEST", raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """compose_brief가 필요로 하는 디렉토리 골격."""
    for sub in ("raw/calendar", "raw/mail", "raw/digest", "harness/traces"):
        (tmp_path / sub).mkdir(parents=True)
    return tmp_path


# ── GET / (chat UI) ─────────────────────────────────────────────────────


def test_webui_serves_html(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "Edith" in body
    assert "Chat" in body and "Brief" in body and "Traces" in body


# ── GET /ui/brief ───────────────────────────────────────────────────────


def test_ui_brief_empty(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    resp = client.get("/ui/brief")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert "Edith" in data["text"]
    assert "일정: 없음" in data["text"]


def test_ui_brief_with_digest(home: Path) -> None:
    (home / "raw" / "digest" / "latest.json").write_text(
        json.dumps({"date": "2026-05-14", "items": [{"title": "테스트 항목", "source": "hn"}]}),
        encoding="utf-8",
    )
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.get("/ui/brief").json()
    assert data["ok"]
    assert "테스트 항목" in data["text"]


# ── GET /ui/traces ──────────────────────────────────────────────────────


def test_ui_traces_empty(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.get("/ui/traces").json()
    assert data["ok"]
    assert data["traces"] == []


def test_ui_traces_lists_summaries(home: Path) -> None:
    trace = {"kind": "start", "task": "테스트 작업", "scope": "personal"}
    fin = {"kind": "finalize", "reason": "end_turn", "cost": 123}
    (home / "harness" / "traces" / "2026-05-14T00-00-00_abc123.jsonl").write_text(
        json.dumps(trace) + "\n" + json.dumps(fin) + "\n", encoding="utf-8"
    )
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.get("/ui/traces").json()
    assert len(data["traces"]) == 1
    t = data["traces"][0]
    assert t["task"] == "테스트 작업"
    assert t["scope"] == "personal"
    assert t["cost_tokens"] == 123
    assert t["finalize_reason"] == "end_turn"


# ── /brief telegram 명령 ────────────────────────────────────────────────


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


def test_telegram_brief_command(home: Path) -> None:
    fake = FakeTelegramClient()
    app = make_app(edith_home=home, secret=SECRET, telegram_client=fake)
    client = TestClient(app)
    payload = {"update_id": 1, "message": {"chat": {"id": 77}, "text": "/brief"}}
    resp = client.post(
        "/webhook/telegram",
        content=json.dumps(payload),
        headers={"x-telegram-bot-api-secret-token": SECRET},
    )
    assert resp.status_code == 200
    assert resp.json()["command"] == "brief"
    assert len(fake.sent) == 1
    chat_id, text = fake.sent[0]
    assert chat_id == 77
    assert "Edith" in text
