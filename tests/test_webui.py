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


# ── /ui/approvals · /ui/approve ─────────────────────────────────────────


def _queue(home: Path) -> Any:
    from harness.approval import ApprovalQueue

    return ApprovalQueue(home / "harness" / "approvals.json")


def test_ui_approvals_empty(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.get("/ui/approvals").json()
    assert data["ok"]
    assert data["approvals"] == []


def test_ui_approvals_lists_pending(home: Path) -> None:
    _queue(home).create(
        action_type="gmail_send", target_system="gmail",
        preview="To: x@y.com\n제목: 테스트", risk_score=7, reversible=False,
    )
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.get("/ui/approvals").json()
    assert len(data["approvals"]) == 1
    a = data["approvals"][0]
    assert a["action_type"] == "gmail_send"
    assert a["risk_score"] == 7
    assert a["reversible"] is False


_WF = (
    "name: x\non:\n  schedule:\n    - cron: '10 22 * * *'\n"
    "jobs:\n  run:\n    runs-on: ubuntu-latest\n"
)


def test_ui_approve_yes_executes(home: Path) -> None:
    """승인(yes) → executor가 실제 action 실행 (F17). github_workflow cron 변경."""
    wf = home / ".github" / "workflows" / "d.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(_WF, encoding="utf-8")
    req = _queue(home).create(
        "github_workflow_update_cron", "github", "cron 변경",
        params={"workflow_path": ".github/workflows/d.yml", "new_cron": "0 21 * * *"},
    )
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    resp = client.post("/ui/approve", json={"id": req.id, "decision": "yes"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "executed"
    assert data["execution"]["ok"] is True
    assert "0 21 * * *" in wf.read_text(encoding="utf-8")  # 실제로 파일 바뀜
    assert _queue(home).get(req.id).status == "executed"


def test_ui_approve_yes_no_executor(home: Path) -> None:
    """executor 없는 action_type — 승인됐으나 실행 실패가 응답에 드러남."""
    req = _queue(home).create("calendar_create", "google_calendar", "일정 생성")
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    data = client.post("/ui/approve", json={"id": req.id, "decision": "yes"}).json()
    assert data["status"] == "executed"
    assert data["execution"]["ok"] is False
    assert "executor 없음" in data["execution"]["error"]


def test_ui_approve_no(home: Path) -> None:
    req = _queue(home).create("gmail_send", "gmail", "메일 발송")
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    resp = client.post("/ui/approve", json={"id": req.id, "decision": "no"})
    assert resp.json()["status"] == "rejected"


def test_ui_approve_bad_input(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    assert client.post("/ui/approve", json={"id": "x"}).status_code == 400
    assert client.post("/ui/approve", json={"decision": "yes"}).status_code == 400


def test_ui_approve_unknown_id(home: Path) -> None:
    client = TestClient(make_app(edith_home=home, secret=SECRET))
    resp = client.post("/ui/approve", json={"id": "nope12345", "decision": "yes"})
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


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
