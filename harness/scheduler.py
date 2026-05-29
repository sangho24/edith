"""F19 — 스케줄러 wiring.

docker edith-cron이 주기적으로 부르는 단일 진입점 `run_tick`. F27 트리거를 평가하고,
체크인 트리거가 발화하면 F26 run_checkin을 돌려 push할 Suggestion을 채널로 보낸다.
모든 발신은 Channel.send의 R5 PII 게이트(F24)를 통과한다.

설계: run_tick은 now·channel을 주입받아 결정성·테스트성을 확보한다(telegram http_post /
relay forward_fn 패턴). cron은 매 N분 `harness tick`을 부르고, tick-window 매칭 +
slot de-dup이 하루 1회 발화를 보장한다.

action→slot 매핑:
- compose_brief  → run_checkin("morning")
- eod_checkin    → run_checkin("evening")
- weekly_synth   → (v1은 콜백만, 합성은 기존 `harness weekly`가 담당 — 중복 발송 방지)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.initiative import run_checkin
from harness.triggers.dispatch import dispatch, load_state, save_state
from harness.triggers.evaluator import evaluate
from harness.triggers.rules import RULES, TriggerRule

# 체크인을 도는 트리거 action → run_checkin slot.
_CHECKIN_SLOTS: dict[str, str] = {
    "compose_brief": "morning",
    "eod_checkin": "evening",
}


def _format_push(suggestion: dict[str, Any]) -> str:
    """Suggestion dict → 사용자에게 보낼 한 줄."""
    title = suggestion.get("title", "")
    why = suggestion.get("why", "")
    return f"• {title}" + (f" — {why}" if why else "")


def run_tick(
    edith_home: Path,
    now_iso: str | None = None,
    channel: Any = None,
    recipient: str | None = None,
    toggles: dict[str, bool] | None = None,
    rules: list[TriggerRule] | None = None,
    tick_seconds: int = 600,
) -> dict[str, Any]:
    """한 tick 처리: 트리거 평가 → 발화 dispatch → 체크인 push.

    Args:
        edith_home: Edith 홈.
        now_iso: 평가 기준 시각 ISO(KST 해석). 기본 now(UTC). 테스트는 주입.
        channel: Channel(send 보유). None이면 push를 collect만(전송 안 함).
        recipient: channel.send 수신자(예: telegram chat_id). channel과 함께 필요.
        toggles: deep_work 등 토글.
        rules: 평가할 룰(기본 RULES).
        tick_seconds: tick 간격(초).

    Returns:
        {"fired": [slot...], "skipped": [...], "pushed": [text...], "checkins": [...]}.
    """
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    rules = rules if rules is not None else RULES
    state = load_state(edith_home)

    fired = evaluate(now, rules, state, tick_seconds=tick_seconds, toggles=toggles)
    result = dispatch(fired, state, rules)
    save_state(edith_home, state)

    pushed: list[str] = []
    checkins: list[dict[str, Any]] = []
    for cb in result["callbacks"]:
        slot = _CHECKIN_SLOTS.get(cb["action"])
        if slot is None:
            continue
        checkin = run_checkin(edith_home, slot, now_iso=now.isoformat())
        checkins.append(checkin)
        for sug in checkin["pushed"]:
            text = _format_push(sug)
            pushed.append(text)
            if channel is not None and recipient is not None:
                # Channel.send가 R5 PII 게이트를 통과시킴(F24).
                channel.send(recipient, text)

    return {
        "fired": result["fired_slots"],
        "skipped": result["skipped"],
        "pushed": pushed,
        "checkins": checkins,
    }


__all__ = ["run_tick"]
