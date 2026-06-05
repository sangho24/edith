"""PR #15 / F16 — MacBook 위에 떠있는 mini FastAPI server.

역할: VPS relay · iPhone (Tailscale 직접) · 브라우저 GUI 의 진입점.

엔드포인트:
- GET  /health             → 살아있는지 확인
- GET  /                    → Web GUI (채팅 UI 단일 페이지, F16)
- GET  /ui/brief            → 오늘 morning brief 텍스트
- GET  /ui/traces           → 최근 trace 요약
- POST /ask                 → {"q": "..."} → harness.runtime.run() 결과 반환
- POST /webhook/telegram    → Telegram update payload 처리 (/start /help /brief + 일반 질문)

운영:
- launchd 로 부팅 시 자동 시작 (scripts/launchd/com.edith.server.plist 추후)
- Tailscale 내부망에서만 노출 권장 (host 127.0.0.1 + Tailscale IP)
- HMAC 검증으로 외부 webhook 정당성 확인. GUI·/ui/* 는 내부망 전용 (서명 불필요)
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

# .env 자동 로드 — uvicorn 직접 실행 시 'source .env' 안 해도 동작.
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass


HELP_TEXT = """🤖 Edith — 개인 비서

💬 자연어로 질문/요청하세요. 적절한 도구를 자동으로 호출합니다.

📋 명령어
/start — 인사
/help  — 이 도움말
/brief — 오늘 아침 브리프 (일정·메일·digest·헬스)

📚 할 수 있는 일 (예시)

📅 일정·메일·digest
• "오늘 일정?" — Apple Calendar 직읽음
• "새 메일 정리해줘" — Gmail (OAuth 후)
• "ds-digest 최신" — 큐레이션 결과

📝 메모·wiki
• "메모: <내용>" — raw/captures 에 저장
• "wiki/INDEX 보여줘" — wiki 페이지 read
• "X 페이지 만들어줘" — wiki 새 페이지 (frontmatter 자동)

🔍 검색·회상
• "X 에 대해 알려줘" — memory_recall (wiki + raw)
• "지난 회의 뭐 했지" — 최근 trace 검색

📰 외부 자료
• "arxiv.org/abs/2407.xxxxx 정리" — 논문 메타데이터
• "이 PR 검토" + 링크 — 코드 리뷰
• "JD: <텍스트>" — 이력서 fit 분석

🚫 외부 쓰기 (정책 R2)
gmail send, calendar create/edit, github commit
→ approval queue 거쳐 /yes <id> 로 승인 후 실행 (Phase 4)

📊 trace 기록
모든 호출은 ~/edith/harness/traces/ 에 JSONL 로.

⚠️ 한도
Gemini Free 5 RPM. 짧은 시간에 많이 보내면 잠시 대기.
"""


def _compose_answer(trace: Any) -> str:
    """trace.output 비었을 때 events 보고 fallback 답변 합성.

    - 정상 종료 + output 있음 → output 그대로
    - 에러 종료 → 에러 카테고리별 사용자 친화 메시지
    - tool 호출은 됐는데 텍스트 출력 없음 (Gemini empty completion 패턴) → 액션 요약
    """
    if trace.output:
        return trace.output

    # 에러로 끝났으면 사용자 친화 메시지
    if trace.finalize_reason == "error":
        for ev in reversed(trace.events):
            if ev.kind == "error":
                msg = ev.payload.get("msg", "알 수 없는 오류")
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    return "⏳ 잠시 후 다시 시도해주세요 (rate limit)"
                if "503" in msg or "UNAVAILABLE" in msg:
                    return "⚠️ 서비스 일시 불안정 — 잠시 후 다시 시도해주세요"
                if "401" in msg or "403" in msg:
                    return "⚠️ 인증 오류 — 관리자 확인 필요"
                return f"⚠️ 오류: {msg[:200]}"
        return "⚠️ 처리 중 오류 발생"

    # tool 호출 있었으면 액션 요약
    actions = [ev for ev in trace.events if ev.kind == "action"]
    if actions:
        names = [ev.payload.get("tool", "?") for ev in actions]
        unique_names = list(dict.fromkeys(names))  # 순서 보존 dedup
        if "capture_text" in unique_names:
            return "✓ 메모로 저장됐습니다."
        if "wiki_write" in unique_names:
            return "✓ wiki 업데이트됐습니다."
        return f"✓ 처리 완료 ({', '.join(unique_names)})"

    if trace.finalize_reason in ("budget_tokens", "budget_steps", "budget_time"):
        return "⏱ 예산 한도 도달 — 더 짧게 다시 물어봐주세요"

    return "(응답 없음 — 다시 시도해주세요)"

try:
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError as e:  # pragma: no cover
    raise RuntimeError("fastapi 필요. uv pip install fastapi uvicorn") from e

_WEBUI_INDEX = Path(__file__).resolve().parent / "webui" / "index.html"


def _brief_text(home: Path) -> str:
    """morning brief 텍스트 — Web GUI와 Telegram /brief 명령이 공유.

    now를 Edith 시간대(KST)로 넘겨 일정·헬스의 '오늘' 창을 사용자 날짜로 고정한다
    (서버가 UTC로 돌아도 KST 자정 부근에 그날 데이터가 누락되지 않게).
    """
    from harness.localtime import edith_now
    from harness.morning import compose_brief

    return compose_brief(home, now=edith_now()).render_text()


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

    # PR #15.1 — TelegramClient 자동 wiring (TELEGRAM_BOT_TOKEN 있으면)
    if telegram_client is None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if token:
            from harness.integrations.telegram import TelegramClient

            chat_id_str = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
            allowed: set[int] | None = (
                {int(chat_id_str)} if chat_id_str.isdigit() else None
            )
            telegram_client = TelegramClient(token=token, allowed_chat_ids=allowed)

    # F13 — TelegramClient를 channel-agnostic Channel 인터페이스로 감싼다.
    # webhook 핸들러는 Channel만 보므로, 새 채널 추가 시 server.py는 안 바뀜.
    from harness.integrations.channel import TelegramChannel

    channel = TelegramChannel(telegram_client) if telegram_client is not None else None

    app = FastAPI(title="Edith Home Hub Server")

    # 실 Gmail/Calendar 호출이 무거워서(메일 50건 fetch ~수초) brief를 90s 캐시.
    # /ui/brief·/ui/summary가 공유. 앱 인스턴스별 캐시라 테스트 격리 안전.
    _brief_cache: dict[str, Any] = {}

    def _cached_brief() -> Any:
        import time

        from harness.localtime import edith_now
        from harness.morning import compose_brief

        hit = _brief_cache.get("b")
        now = time.time()
        if hit is not None and now - hit[0] < 90:
            return hit[1]
        brief = compose_brief(home, now=edith_now())
        _brief_cache["b"] = (now, brief)
        return brief

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "edith_home": str(home),
            "secret_configured": bool(secret),
            "telegram_configured": telegram_client is not None,
        }

    # ── F16 Web GUI — Tailscale 내부망에서 브라우저로 Edith 조작 ──────
    @app.get("/", response_class=HTMLResponse)
    def webui() -> HTMLResponse:
        """채팅 UI 단일 페이지. /ask·/ui/* 엔드포인트를 호출."""
        if not _WEBUI_INDEX.exists():  # pragma: no cover
            return HTMLResponse("<h1>Edith</h1><p>webui/index.html 없음</p>", status_code=500)
        return HTMLResponse(_WEBUI_INDEX.read_text(encoding="utf-8"))

    @app.get("/ui/brief")
    def ui_brief() -> dict[str, Any]:
        """오늘 morning brief 텍스트 (GUI Brief 탭). 90s 캐시."""
        try:
            return {"ok": True, "text": _cached_brief().render_text()}
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": str(e)}

    @app.get("/ui/summary")
    def ui_summary() -> dict[str, Any]:
        """대시보드 홈 카드용 구조화 요약 (일정·메일·digest·헬스·제안·승인 카운트)."""
        try:
            from harness.integrations.apple_health import format_for_brief

            b = _cached_brief()
            props = _proposal_store().list(status="proposed")
            queue = _approval_queue()
            queue.expire_old()
            return {
                "ok": True,
                "date": b.today_str,
                "events_n": b.today.get("n_events", 0),
                "events": [e.get("summary", "") for e in b.today.get("events", [])[:4]],
                "busy_min": b.today.get("total_busy_minutes", 0),
                "unread": b.mail_summary.get("n_unread", 0),
                "mail_by_priority": b.mail_summary.get("by_priority", {}),
                "digest_n": b.digest.get("n", 0),
                "health": format_for_brief(b.health) if b.health else "",
                "top3": b.top3,
                "proposals": len(props),
                "approvals": len(queue.list(status="pending")),
            }
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": str(e)}

    @app.get("/ui/traces")
    def ui_traces(last: int = 20) -> dict[str, Any]:
        """최근 trace 요약 (GUI Traces 탭)."""
        from harness.traces import list_traces

        summaries = list_traces(home / "harness" / "traces", last=last)
        return {
            "ok": True,
            "traces": [
                {
                    "id": s.id,
                    "task": s.task,
                    "scope": s.scope,
                    "n_steps": s.n_steps_action,
                    "n_blocked": s.n_blocked,
                    "cost_tokens": s.cost_tokens,
                    "finalize_reason": s.finalize_reason,
                }
                for s in reversed(summaries)
            ],
        }

    def _approval_queue() -> Any:
        from harness.approval import ApprovalQueue

        return ApprovalQueue(home / "harness" / "approvals.json")

    @app.get("/ui/approvals")
    def ui_approvals() -> dict[str, Any]:
        """pending 승인 요청 목록 (GUI Approvals 탭). 만료된 건 먼저 정리."""
        queue = _approval_queue()
        queue.expire_old()
        return {
            "ok": True,
            "approvals": [
                {
                    "id": r.id,
                    "action_type": r.action_type,
                    "target_system": r.target_system,
                    "preview": r.preview,
                    "risk_score": r.risk_score,
                    "reversible": r.reversible,
                    "scope": r.scope,
                    "requested_at": r.requested_at,
                    "expires_at": r.expires_at,
                }
                for r in queue.list(status="pending")
            ],
        }

    @app.post("/ui/approve")
    async def ui_approve(request: Request) -> JSONResponse:
        """승인 큐 항목 승인/거절. body: {"id": ..., "decision": "yes"|"no"}."""
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        req_id = payload.get("id", "")
        decision = payload.get("decision", "")
        if not req_id or decision not in ("yes", "no"):
            raise HTTPException(status_code=400, detail="id + decision(yes|no) required")
        queue = _approval_queue()

        if decision == "no":
            try:
                r = queue.reject(req_id)
            except (KeyError, ValueError) as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
            return JSONResponse({"ok": True, "id": r.id, "status": r.status})

        # decision == "yes" — 승인 후 executor가 실제 action 실행 (F17).
        try:
            queue.approve(req_id)
        except (KeyError, ValueError) as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        from harness.executor import ApprovalExecutor

        result = ApprovalExecutor(queue, home).execute(req_id)
        final = queue.get(req_id)
        return JSONResponse(
            {
                "ok": True,
                "id": req_id,
                "status": final.status if final else "unknown",
                "execution": {
                    "ok": result.ok,
                    "detail": result.detail,
                    "error": result.error,
                },
            }
        )

    # ── F28 워크플로우 제안 ──────────────────────────────────────────
    def _proposal_store() -> Any:
        from harness.propose import ProposalStore

        return ProposalStore(home / "harness" / "proposals.json")

    @app.get("/ui/proposals")
    def ui_proposals() -> dict[str, Any]:
        """proposed 상태 제안 목록 (GUI Proposals 탭)."""
        store = _proposal_store()
        return {
            "ok": True,
            "proposals": [
                {
                    "id": p.id,
                    "title": p.title,
                    "scope": p.scope,
                    "rationale": p.rationale,
                    "steps": [
                        {
                            "idx": s.idx,
                            "intent": s.intent,
                            "explanation": s.explanation,
                            "expected_outcome": s.expected_outcome,
                            "risk_note": s.risk_note,
                            "support_refs": s.support_refs,
                            "action_type": s.action_type,
                            "reversible": s.reversible,
                            "risk_score": s.risk_score,
                            "inferred": s.inferred,
                        }
                        for s in p.steps
                    ],
                }
                for p in store.list(status="proposed")
            ],
        }

    @app.post("/ui/proposals/decide")
    async def ui_proposals_decide(request: Request) -> JSONResponse:
        """제안 승인/거절. body: {id, decision: accept|reject, accepted_steps?: [idx]}.

        accept 시 (선택된) step별로 ApprovalQueue에 pending 등록 — 자동 실행 안 함
        ("승인만"). 실제 실행은 Approvals 탭에서. external write가 아닌(action_type 빈)
        step은 큐 생성 생략(즉시 처리 대상 아님 — v1은 큐 등록만 추적).
        """
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        pid = payload.get("id", "")
        decision = payload.get("decision", "")
        if not pid or decision not in ("accept", "reject"):
            raise HTTPException(status_code=400, detail="id + decision(accept|reject) required")

        store = _proposal_store()
        proposal = store.get(pid)
        if proposal is None or proposal.status != "proposed":
            return JSONResponse(
                {"ok": False, "error": "제안 없음 또는 이미 처리됨"}, status_code=400
            )

        if decision == "reject":
            store.close(pid)
            return JSONResponse({"ok": True, "id": pid, "status": "rejected"})

        accepted = payload.get("accepted_steps")  # None이면 전체
        queue = _approval_queue()
        queued: list[str] = []
        for step in proposal.steps:
            if accepted is not None and step.idx not in accepted:
                continue
            if not step.action_type:
                continue  # internal step — 큐 대상 아님
            req = queue.create(
                action_type=step.action_type,
                target_system=step.action_type.split("_")[0],
                preview=step.preview(),
                params=step.params,
                risk_score=step.risk_score,
                reversible=step.reversible,
                scope=proposal.scope,
            )
            queued.append(req.id)
        store.close(pid)
        return JSONResponse(
            {"ok": True, "id": pid, "status": "accepted", "queued_approvals": queued,
             "note": "승인 큐에 등록됨 — Approvals 탭에서 실행."}
        )

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
        """Telegram update payload 처리.

        인증 두 가지 path:
        1. Telegram 직접 (Funnel/Tunnel 통해) —
           X-Telegram-Bot-Api-Secret-Token 헤더 (단순 토큰 비교)
        2. VPS relay 경유 — X-Relay-Signature 헤더 (HMAC-SHA256 검증)

        흐름:
        1. 인증
        2. update parse → chat_id, text
        3. text 를 task 로 runtime.run() (또는 큐잉)
        4. 결과를 sendMessage 로 답신
        """
        body = await request.body()
        tg_secret_token = request.headers.get("x-telegram-bot-api-secret-token")
        if secret:
            valid_tg = tg_secret_token == secret
            valid_hmac = _verify_signature(body, x_relay_signature, secret)
            if not (valid_tg or valid_hmac):
                raise HTTPException(status_code=401, detail="invalid signature")

        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e

        if channel is None:
            return JSONResponse(
                {"ok": True, "note": "telegram_client 미설정 — payload received but skipped"}
            )

        msg = channel.parse_incoming(payload)
        if msg is None:
            return JSONResponse({"ok": True, "skipped": True})

        # 명령 / 일반 메시지 분기
        if msg.text.startswith("/start"):
            channel.send(
                msg.sender_id,
                "안녕하세요 — Edith 봇입니다. /help 로 사용법 확인.",
            )
            return JSONResponse({"ok": True, "command": "start"})

        if msg.text.startswith("/help"):
            channel.send(msg.sender_id, HELP_TEXT)
            return JSONResponse({"ok": True, "command": "help"})

        if msg.text.startswith("/brief"):
            try:
                channel.send(msg.sender_id, _brief_text(home))
            except Exception as e:
                channel.send(msg.sender_id, f"brief 생성 오류: {e}")
            return JSONResponse({"ok": True, "command": "brief"})

        # 일반 질문 — runtime 호출
        if runner is None:
            from harness.runtime import run as runtime_run

            run_fn = runtime_run
        else:
            run_fn = runner

        try:
            trace = run_fn(msg.text, edith_home=home)
            answer = _compose_answer(trace)
            channel.send(msg.sender_id, answer)
            return JSONResponse(
                {"ok": True, "trace_id": trace.id, "answered": True}
            )
        except Exception as e:
            channel.send(msg.sender_id, f"오류: {e}")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    return app


# 운영용 — uvicorn harness.server:app --host 0.0.0.0 --port 8765
app = make_app()
