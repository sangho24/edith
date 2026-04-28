"""Phase 3 F12 — VPS Relay tests (FastAPI TestClient, no real network)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

# fastapi/uvicorn은 sandbox에 없을 수 있음 — 조건부 skip
try:
    from fastapi.testclient import TestClient

    from vps.relay import _verify_signature, make_app
except ImportError:
    pytest.skip("fastapi 또는 vps.relay import 실패", allow_module_level=True)


SECRET = "test-secret-32-bytes-or-more-pls"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── _verify_signature ──


def test_verify_valid() -> None:
    body = b'{"text": "hi"}'
    assert _verify_signature(body, _sign(body), SECRET)


def test_verify_invalid() -> None:
    body = b'{"text": "hi"}'
    wrong = "sha256=" + "0" * 64
    assert not _verify_signature(body, wrong, SECRET)


def test_verify_missing() -> None:
    assert not _verify_signature(b"x", None, SECRET)


def test_verify_wrong_format() -> None:
    assert not _verify_signature(b"x", "md5=abc", SECRET)


# ── /health ──


def test_health_ok() -> None:
    app = make_app(secret=SECRET, home_hub_url="http://hub:8000")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["secret_configured"]
    assert data["hub_configured"]


def test_health_unconfigured() -> None:
    app = make_app(secret="", home_hub_url="")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.json()["secret_configured"] is False


# ── /webhook ──


def test_webhook_with_valid_sig() -> None:
    received: list[tuple[str, dict]] = []

    def fake_forward(source: str, payload: dict) -> None:
        received.append((source, payload))

    app = make_app(secret=SECRET, forward_fn=fake_forward)
    client = TestClient(app)

    body = json.dumps({"event": "push", "ref": "main"}).encode()
    resp = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    assert resp.json()["forwarded"]
    assert received == [("github", {"event": "push", "ref": "main"})]


def test_webhook_invalid_sig_rejected() -> None:
    app = make_app(secret=SECRET, forward_fn=lambda s, p: None)
    client = TestClient(app)
    resp = client.post(
        "/webhook/github",
        content=b"{}",
        headers={"X-Relay-Signature": "sha256=" + "0" * 64},
    )
    assert resp.status_code == 401


def test_webhook_no_secret_skips_verification() -> None:
    """secret 미설정이면 모든 요청 통과 (dev 모드)."""
    received: list[tuple[str, dict]] = []
    app = make_app(secret="", forward_fn=lambda s, p: received.append((s, p)))
    client = TestClient(app)
    resp = client.post("/webhook/x", json={"a": 1})
    assert resp.status_code == 200
    assert received == [("x", {"a": 1})]


# ── /push/kakao ──


def test_push_kakao() -> None:
    captured: dict = {}

    def fake_forward(source: str, payload: dict) -> str:
        captured["source"] = source
        captured["payload"] = payload
        return "ok"

    app = make_app(secret=SECRET, forward_fn=fake_forward)
    client = TestClient(app)

    body = json.dumps({"text": "오늘 brief: 일정 3건"}).encode()
    resp = client.post(
        "/push/kakao",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 200
    assert captured["source"] == "kakao_memo"
    assert "오늘 brief" in captured["payload"]["text"]


def test_push_kakao_text_required() -> None:
    app = make_app(secret=SECRET, forward_fn=lambda s, p: None)
    client = TestClient(app)
    body = json.dumps({}).encode()
    resp = client.post(
        "/push/kakao",
        content=body,
        headers={"X-Relay-Signature": _sign(body)},
    )
    assert resp.status_code == 400


def test_push_kakao_invalid_sig() -> None:
    app = make_app(secret=SECRET)
    client = TestClient(app)
    resp = client.post(
        "/push/kakao",
        json={"text": "hi"},
        headers={"X-Relay-Signature": "sha256=bad"},
    )
    assert resp.status_code == 401


# ── /oauth callback ──


def test_oauth_callback_forwards_params() -> None:
    captured: dict = {}

    def fake_forward(source: str, payload: dict) -> None:
        captured[source] = payload

    app = make_app(forward_fn=fake_forward)
    client = TestClient(app)
    resp = client.get("/oauth/google/callback?code=abc123&state=xyz")
    assert resp.status_code == 200
    assert resp.json()["provider"] == "google"
    assert captured["oauth_google"]["code"] == "abc123"
    assert captured["oauth_google"]["state"] == "xyz"
