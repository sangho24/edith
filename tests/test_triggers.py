"""F27 컨텍스트 트리거 v1 — evaluate 순수함수 + dispatch de-dup 테스트.

시각은 모두 인자(now)로 주입해 결정성을 보장한다(datetime.now() 직접 호출 없음).
now는 KST로 해석한다(rules.py의 cron도 KST 기준).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from harness.triggers.dispatch import dispatch, load_state, save_state
from harness.triggers.evaluator import _cron_weekday, _in_quiet_hours, evaluate, evaluate_iso
from harness.triggers.rules import RULES, FiredTrigger, TriggerRule

# ── 테스트용 룰 ──

MORNING = TriggerRule(
    name="morning_brief",
    kind="cron",
    schedule="0 8 * * 1-5",  # 평일 08:00
    action="compose_brief",
    channel="telegram",
    scope="personal",
    toggle_key="deep_work",
)
DAILY_NINE = TriggerRule(
    name="eod_checkin",
    kind="cron",
    schedule="0 21 * * *",  # 매일 21:00
    action="eod_checkin",
    channel="telegram",
    scope="personal",
    toggle_key="deep_work",
)
NIGHT_RULE = TriggerRule(
    name="night_ping",
    kind="cron",
    schedule="0 23 * * *",  # 매일 23:00
    action="ping",
    channel="telegram",
    scope="personal",
    quiet_hours=(22, 7),  # 야간 무음 22:00~07:00
)


# 2026-05-29는 금요일 → cron weekday 5.
FRIDAY_0800 = datetime(2026, 5, 29, 8, 0, 0)
# 2026-05-31은 일요일 → cron weekday 0.
SUNDAY_2200 = datetime(2026, 5, 31, 22, 0, 0)


# ── _cron_weekday ──


def test_cron_weekday_mapping() -> None:
    # 일요일=0, 월=1, ... 토=6
    assert _cron_weekday(datetime(2026, 5, 31, 0, 0)) == 0  # Sunday
    assert _cron_weekday(datetime(2026, 5, 25, 0, 0)) == 1  # Monday
    assert _cron_weekday(datetime(2026, 5, 29, 0, 0)) == 5  # Friday
    assert _cron_weekday(datetime(2026, 5, 30, 0, 0)) == 6  # Saturday


# ── tick-window 매칭 ──


def test_exact_minute_fires() -> None:
    fired = evaluate(FRIDAY_0800, rules=[MORNING], state={"fired": []})
    assert [f.rule_name for f in fired] == ["morning_brief"]


def test_within_window_fires() -> None:
    """08:04 — tick 600s(±300s) 안 → 발화."""
    now = datetime(2026, 5, 29, 8, 4, 0)
    fired = evaluate(now, rules=[MORNING], state={"fired": []}, tick_seconds=600)
    assert len(fired) == 1


def test_before_window_fires() -> None:
    """07:56 — 발화 시각 -240s, ±300s 안 → 발화."""
    now = datetime(2026, 5, 29, 7, 56, 0)
    fired = evaluate(now, rules=[MORNING], state={"fired": []}, tick_seconds=600)
    assert len(fired) == 1


def test_outside_window_no_fire() -> None:
    """08:06 — 발화 시각 +360s, ±300s 밖 → 발화 안 함."""
    now = datetime(2026, 5, 29, 8, 6, 0)
    fired = evaluate(now, rules=[MORNING], state={"fired": []}, tick_seconds=600)
    assert fired == []


def test_smaller_tick_narrows_window() -> None:
    """tick 60s(±30s)이면 08:04는 발화 안 함."""
    now = datetime(2026, 5, 29, 8, 4, 0)
    fired = evaluate(now, rules=[MORNING], state={"fired": []}, tick_seconds=60)
    assert fired == []


def test_weekday_rule_skips_sunday() -> None:
    """평일 룰은 일요일엔 발화 안 함."""
    now = datetime(2026, 5, 31, 8, 0, 0)  # Sunday
    fired = evaluate(now, rules=[MORNING], state={"fired": []})
    assert fired == []


def test_sunday_dow_rule_fires_on_sunday() -> None:
    weekly = TriggerRule(
        name="weekly_synth",
        kind="cron",
        schedule="0 22 * * 0",
        action="weekly_synth",
        channel="telegram",
        scope="personal",
    )
    fired = evaluate(SUNDAY_2200, rules=[weekly], state={"fired": []})
    assert [f.rule_name for f in fired] == ["weekly_synth"]
    # 금요일엔 발화 안 함
    assert evaluate(FRIDAY_0800, rules=[weekly], state={"fired": []}) == []


def test_daily_rule_fires_any_day() -> None:
    now = datetime(2026, 5, 31, 21, 0, 0)  # Sunday 21:00
    fired = evaluate(now, rules=[DAILY_NINE], state={"fired": []})
    assert len(fired) == 1


# ── de-dup ──


def test_dedup_same_slot_no_refire() -> None:
    slot = "2026-05-29_morning_brief"
    fired = evaluate(FRIDAY_0800, rules=[MORNING], state={"fired": [slot]})
    assert fired == []


def test_dedup_different_day_fires() -> None:
    """전날 발화 기록은 오늘 발화를 막지 않음."""
    slot = "2026-05-28_morning_brief"
    fired = evaluate(FRIDAY_0800, rules=[MORNING], state={"fired": [slot]})
    assert len(fired) == 1


# ── quiet hours ──


def test_in_quiet_hours_helper() -> None:
    # 자정 횡단 (22,7): 23시·6시는 무음, 8시는 아님
    assert _in_quiet_hours(23, (22, 7)) is True
    assert _in_quiet_hours(6, (22, 7)) is True
    assert _in_quiet_hours(8, (22, 7)) is False
    # 일반 구간 (9,18)
    assert _in_quiet_hours(10, (9, 18)) is True
    assert _in_quiet_hours(18, (9, 18)) is False
    assert _in_quiet_hours(5, None) is False


def test_quiet_hours_skips_fire() -> None:
    """23:00 발화 룰이 야간 무음(22~07) 안 → skip."""
    now = datetime(2026, 5, 29, 23, 0, 0)
    fired = evaluate(now, rules=[NIGHT_RULE], state={"fired": []})
    assert fired == []


def test_quiet_hours_none_allows_fire() -> None:
    """quiet_hours 없는 룰은 같은 시각에 발화."""
    r = TriggerRule(
        name="late",
        kind="cron",
        schedule="0 23 * * *",
        action="ping",
        channel="telegram",
        scope="personal",
    )
    now = datetime(2026, 5, 29, 23, 0, 0)
    fired = evaluate(now, rules=[r], state={"fired": []})
    assert len(fired) == 1


# ── toggle ──


def test_toggle_skips_fire() -> None:
    """deep_work=True면 morning_brief skip."""
    fired = evaluate(
        FRIDAY_0800, rules=[MORNING], state={"fired": []}, toggles={"deep_work": True}
    )
    assert fired == []


def test_toggle_false_allows_fire() -> None:
    fired = evaluate(
        FRIDAY_0800, rules=[MORNING], state={"fired": []}, toggles={"deep_work": False}
    )
    assert len(fired) == 1


def test_toggle_none_key_unaffected() -> None:
    """toggle_key=None인 룰은 toggles와 무관하게 발화."""
    weekly = TriggerRule(
        name="weekly_synth",
        kind="cron",
        schedule="0 22 * * 0",
        action="weekly_synth",
        channel="telegram",
        scope="personal",
        toggle_key=None,
    )
    fired = evaluate(SUNDAY_2200, rules=[weekly], state={"fired": []}, toggles={"deep_work": True})
    assert len(fired) == 1


# ── 기본 RULES smoke ──


def test_default_rules_morning_fires_on_weekday() -> None:
    fired = evaluate(FRIDAY_0800, state={"fired": []})
    assert "morning_brief" in [f.rule_name for f in fired]


def test_evaluate_pure_does_not_mutate_state() -> None:
    state = {"fired": []}
    evaluate(FRIDAY_0800, rules=[MORNING], state=state)
    assert state == {"fired": []}  # evaluate는 state 미변경


# ── evaluate_iso (golden 진입점) ──


def test_evaluate_iso_returns_dict() -> None:
    out = evaluate_iso("2026-05-29T08:00:00", state={"fired": []})
    assert out["n"] >= 1
    assert "morning_brief" in out["names"]


def test_evaluate_iso_dedup() -> None:
    out = evaluate_iso(
        "2026-05-29T08:00:00",
        rules=None,
        state={"fired": ["2026-05-29_morning_brief"]},
    )
    assert "morning_brief" not in out["names"]


# ── dispatch ──


def _ft(name: str, when: datetime) -> FiredTrigger:
    return FiredTrigger(rule_name=name, fired_at=when, reason="test")


def test_dispatch_records_slot_and_callback() -> None:
    state: dict = {"fired": []}
    res = dispatch([_ft("morning_brief", FRIDAY_0800)], state, rules=RULES)
    assert res["fired_slots"] == ["2026-05-29_morning_brief"]
    assert state["fired"] == ["2026-05-29_morning_brief"]
    cb = res["callbacks"][0]
    assert cb["action"] == "compose_brief"
    assert cb["channel"] == "telegram"
    assert cb["scope"] == "personal"


def test_dispatch_dedup_skips_recorded_slot() -> None:
    state: dict = {"fired": ["2026-05-29_morning_brief"]}
    res = dispatch([_ft("morning_brief", FRIDAY_0800)], state, rules=RULES)
    assert res["callbacks"] == []
    assert res["skipped"] == ["2026-05-29_morning_brief"]
    # 중복 기록 안 함
    assert state["fired"] == ["2026-05-29_morning_brief"]


def test_dispatch_idempotent_twice() -> None:
    """같은 발화를 두 번 dispatch해도 slot은 한 번만."""
    state: dict = {"fired": []}
    fired = [_ft("eod_checkin", datetime(2026, 5, 29, 21, 0))]
    dispatch(fired, state, rules=RULES)
    res2 = dispatch(fired, state, rules=RULES)
    assert res2["callbacks"] == []
    assert state["fired"].count("2026-05-29_eod_checkin") == 1


def test_dispatch_unknown_rule_callback_has_none_fields() -> None:
    state: dict = {"fired": []}
    res = dispatch([_ft("ghost", FRIDAY_0800)], state, rules=RULES)
    cb = res["callbacks"][0]
    assert cb["action"] is None
    assert cb["rule_name"] == "ghost"


# ── load_state / save_state ──


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    state = {"fired": ["2026-05-29_morning_brief"]}
    path = save_state(tmp_path, state)
    assert path.exists()
    loaded = load_state(tmp_path)
    assert loaded["fired"] == ["2026-05-29_morning_brief"]


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_state(tmp_path) == {"fired": []}


def test_load_corrupt_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "harness" / "trigger_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert load_state(tmp_path) == {"fired": []}
