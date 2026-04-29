"""PR #15 — MacBook 위에 떠있는 mini FastAPI server.

역할: VPS relay 또는 iPhone (Tailscale 직접) 의 진입점.

엔드포인트:
- GET  /health             → 살아있는지 확인
- POST /ask                 → {"q": "..."} → harness.runtime.run() 결과 반환
- POST /webhook/telegram    → Telegram update payload 받아 처리 (relay 통해 forward 된 거)

운영:
- launchd 로 부팅 시 자동 시작 (scripts/launchd/com.edith.server.plist 추후)
- Tailscale 내부망에서만 노출 권장 (host 127.0.0.1 + Tailscale IP)
- HMAC 검증으로 외부 webhook 정당성 확인
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError as e:  # pragma: no cover
    raise RuntimeError("fastapi 필요. uv pip install fastapi uvicorn") from e


def _verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """HMAC-SHA256 검증 (vps/relay.py 와 동일 포맷)."""
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    given = signature[len("sha256=") :]
    return hmac.compare_digest(expected, given)


def make_app(
    edith_home: Path | None = None,
    secret: str | None = None,
    runner: Any = None,
    telegram_client: Any = None,
) -> FastAPI:
    """Server factory.

    runner: callable(task: str, edith_home: Path) -> Trace.  None 이면 import.
    telegram_client: TelegramClient 인스턴스. None 이면 webhook 응답만 큐잉.
    """
    home = edith_home or Path(os.environ.get("EDITH_HOME", str(Path.home() / "edith")))
    # ⚠️ 명시적 None 체크 — secret="" 은 dev 모드 의도. env leak 방지.
    if secret is None:
        secret = os.environ.get("RELAY_SECRET", "")

    app = FastAPI(title="Edith Home Hub Server")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "edith_home": str(home),
            "secret_configured": bool(secret),
            "telegram_configured": telegram_client is not None,
        }

    @app.post("/ask")
    async def ask(request: Request) -> JSONResponse:
        """단순 query 진입점. iPhone Shortcut / Telegram 등."""
        body = await request.body()

        # 외부 (relay 거친 요청) 면 secret 검증. 내부 (Tailscale only) 면 skip.
        signature = request.headers.get("x-relay-signature")
        if signature is not None:
            if not secret or not _verify_signature(body, signature, secret):
                raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e

        question = payload.get("q") or payload.get("question") or ""
        if not question.strip():
            raise HTTPException(status_code=400, detail="q required")

        if runner is None:
            from harness.runtime import run as runtime_run

            run_fn = runtime_run
        else:
            run_fn = runner

        try:
            trace = run_fn(question, edith_home=home)
            return JSONResponse(
                {
                    "ok": True,
                    "answer": trace.output or "",
                    "steps": trace.n_steps,
                    "tokens": trace.cost_tokens,
                    "trace_id": trace.id,
                }
            )
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.post("/webhook/telegram")
    async def telegram_webhook(
        request: Request,
        x_relay_signature: str | None = Header(default=None),
    ) -> JSONResponse:
        """Telegram update payload (relay 통해 forward 된 것) 처리.

        흐름:
        1. HMAC 검증
        2. update parse → chat_id, text
        3. text 를 task 로 runtime.run() (또는 큐잉)
        4. 결과를 sendMessage 로 답신
        """
        body = await request.body()
        if secret and not _verify_signature(body, x_relay_signature, secret):
            raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e

        if telegram_client is None:
            return JSONResponse(
                {"ok": True, "note": "telegram_client 미설정 — payload received but skipped"}
            )

        update = telegram_client.parse_update(payload)
        if update is None:
            return JSONResponse({"ok": True, "skipped": True})

        # 명령 / 일반 메시지 분기
        if update.text.startswith("/start"):
            telegram_client.send_message(
                update.chat_id,
                "안녕하세요 — Edith 봇입니다. 질문 보내시면 답변드릴게요.",
            )
            return JSONResponse({"ok": True, "command": "start"})

        # 일반 질문 — runtime 호출
        if runner is None:
            from harness.runtime import run as runtime_run

            run_fn = runtime_run
        else:
            run_fn = runner

        try:
            trace = run_fn(update.text, edith_home=home)
            answer = trace.output or "(응답 없음)"
            telegram_client.send_message(update.chat_id, answer)
            return JSONResponse(
                {"ok": True, "trace_id": trace.id, "answered": True}
            )
        except Exception as e:
            telegram_client.send_message(update.chat_id, f"오류: {e}")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return app


# 운영용 — uvicorn harness.server:app --host 0.0.0.0 --port 8765
app = make_app()
