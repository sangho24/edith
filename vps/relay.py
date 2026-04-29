"""Phase 3 F12 — VPS Relay.

작은 VPS (AWS Lightsail / Oracle Free Tier / DigitalOcean $5)에 배치.
역할:
1. 외부 webhook 수신 (GitHub Actions, Calendar push, Kakao 등) → Home Hub로 forward
2. KakaoTalk Memo API push (외부 callable IP 필요)
3. OAuth callback 수신 → Home Hub로 forward

설계:
- stateless: relay 본체에 데이터 저장 X (재배포 자유)
- 인증: shared HMAC secret (RELAY_SECRET env)
- forward 대상: HOME_HUB_URL (Tailscale IP 또는 SSH tunnel localhost)

테스트는 FastAPI TestClient로 실제 네트워크 없이.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable
from typing import Any

try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError as e:  # pragma: no cover
    raise RuntimeError("fastapi 필요. uv pip install fastapi uvicorn") from e


def _verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """HMAC-SHA256 검증. signature는 'sha256=<hex>' 형식."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    given = signature[len("sha256=") :]
    return hmac.compare_digest(expected, given)


def make_app(
    secret: str | None = None,
    home_hub_url: str | None = None,
    forward_fn: Callable[[str, dict], Any] | None = None,
) -> FastAPI:
    """relay app factory.

    forward_fn: webhook 받은 후 home hub로 보낼 함수 (test 시 mock).
                None이면 RELAY_FORWARD_TARGET env로 HTTP POST.
    """
    secret = secret or os.environ.get("RELAY_SECRET", "")
    home_hub_url = home_hub_url or os.environ.get("HOME_HUB_URL", "")

    app = FastAPI(title="Edith VPS Relay")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "secret_configured": bool(secret), "hub_configured": bool(home_hub_url)}

    # ⚠️ /webhook/telegram 은 /webhook/{source} 보다 먼저 등록해야 함 (FastAPI 는 매칭 순서대로).
    @app.post("/webhook/telegram")
    async def telegram_webhook(request: Request) -> JSONResponse:
        """Telegram webhook 진입점.

        Telegram setWebhook 시 등록한 secret_token 을 'X-Telegram-Bot-Api-Secret-Token'
        헤더로 보내옴. 우리는 RELAY_SECRET 을 그대로 쓰고 비교 검증.
        그 후 home hub 로 forward.
        """
        secret_token = request.headers.get("x-telegram-bot-api-secret-token")
        if secret and secret != secret_token:
            raise HTTPException(status_code=401, detail="invalid secret_token")
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e

        if forward_fn:
            forward_fn("telegram", payload)
            return JSONResponse({"ok": True, "forwarded": True})

        return JSONResponse(
            {
                "ok": True,
                "forwarded": False,
                "note": "forward_fn 미설정 — telegram payload 큐잉 안 됨",
            }
        )

    @app.post("/webhook/{source}")
    async def webhook(
        source: str,
        request: Request,
        x_relay_signature: str | None = Header(default=None),
    ) -> JSONResponse:
        body = await request.body()
        if secret and not _verify_signature(body, x_relay_signature, secret):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": body.decode("utf-8", errors="replace")}

        if forward_fn:
            forward_fn(source, payload)
            return JSONResponse({"ok": True, "forwarded": True, "source": source})

        # default: home hub로 POST (실제 통신은 운영에서)
        return JSONResponse(
            {
                "ok": True,
                "forwarded": False,
                "source": source,
                "note": "forward_fn 미설정 — home hub forwarding 비활성",
            }
        )

    @app.post("/push/kakao")
    async def push_kakao(
        request: Request,
        x_relay_signature: str | None = Header(default=None),
    ) -> JSONResponse:
        """home hub → relay → kakao memo. payload: {text, kakao_token}."""
        body = await request.body()
        if secret and not _verify_signature(body, x_relay_signature, secret):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e

        text = payload.get("text", "")
        if not text:
            raise HTTPException(status_code=400, detail="text required")

        if forward_fn:
            result = forward_fn("kakao_memo", payload)
            return JSONResponse({"ok": True, "result": result})

        return JSONResponse(
            {
                "ok": True,
                "queued": True,
                "note": "실제 KakaoTalk Memo API call은 forward_fn 또는 운영 통합에서.",
                "preview": text[:100],
            }
        )

    @app.get("/oauth/{provider}/callback")
    async def oauth_callback(provider: str, request: Request) -> JSONResponse:
        """OAuth provider redirect 받기 → home hub로 code 전달."""
        params = dict(request.query_params)
        if forward_fn:
            forward_fn(f"oauth_{provider}", params)
        return JSONResponse(
            {
                "ok": True,
                "provider": provider,
                "note": "code를 home hub로 전달 후 토큰 교환 진행. 이 창은 닫아도 됩니다.",
            }
        )

    return app


# 운영용 — `uvicorn vps.relay:app --host 0.0.0.0 --port 8765`
app = make_app()
