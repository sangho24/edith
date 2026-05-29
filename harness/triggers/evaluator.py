"""F27 트리거 평가기 — now·rules·state → 발화 목록(FiredTrigger). 순수함수.

핵심: evaluate()는 부수효과 없음. 시각은 인자(now)로 주입한다.
tick-window 매칭: 스케줄러가 정확히 발화 시각(exact minute)에 깨어난다는 보장이 없으므로
now가 cron 발화 시각 ± tick_seconds/2 안이면 발화로 본다.

de-dup: 같은 slot(=날짜+rule_name)이 state["fired"]에 있으면 재발화하지 않는다
(한 tick-window가 여러 tick에 걸쳐도 하루 한 번만).

now는 **KST**로 해석한다(rules.py의 cron도 KST 기준). naive/aware 모두 허용 —
요일·시·분 필드만 본다.
"""

from __future__ import annotations

from datetime import datetime

from harness.integrations.github_workflow import parse_cron_to_kst
from harness.triggers.rules import RULES, FiredTrigger, TriggerRule


def _parse_schedule(schedule: str) -> tuple[int, int, str] | None:
    """cron(`분 시 일 월 요일`) → (minute, hour, dow_field). 파싱 불가면 None.

    daily cron(요일 `*`)은 github_workflow.parse_cron_to_kst를 재사용해 시·분을 얻는다.
    단 parse_cron_to_kst는 일·월·요일이 모두 `*`인 순수 daily cron만 처리하고,
    요일 cron(예: `0 8 * * 1-5`)은 None을 돌려준다(요일 cron 한계). 따라서 요일
    필드가 `*`가 아니면 여기서 직접 분/시를 파싱한다.

    주의: parse_cron_to_kst는 cron을 'UTC' 기준으로 보고 KST(+9)로 변환하지만,
    여기서는 cron 자체를 KST로 정의하므로 시각 변환이 아니라 '숫자 파싱'만 필요하다.
    그래서 daily 경로에서도 parse_cron_to_kst의 반환을 그대로 쓰지 않고, 파싱
    성공 여부 판정에만 활용한 뒤 raw 필드를 직접 읽는다.
    """
    parts = schedule.strip().split()
    if len(parts) != 5:
        return None
    minute_str, hour_str, dom, mon, dow = parts
    if not (minute_str.isdigit() and hour_str.isdigit()):
        return None
    if (dom, mon) != ("*", "*"):
        return None  # v1: 일·월 한정 cron 미지원

    # daily cron(요일 *)이면 parse_cron_to_kst로 형식 유효성을 한 번 더 확인.
    # (요일이 *가 아니면 parse_cron_to_kst가 None → 우리가 직접 파싱.)
    if dow == "*":
        kst = parse_cron_to_kst(f"{minute_str} {hour_str} * * *")
        if kst is None:
            return None

    minute = int(minute_str)
    hour = int(hour_str)
    if not (0 <= minute <= 59 and 0 <= hour <= 23):
        return None
    return minute, hour, dow


def _dow_matches(dow_field: str, weekday_cron: int) -> bool:
    """cron 요일 필드가 주어진 요일(0=일..6=토)에 매치되는지.

    지원: `*`, 단일 숫자(`0`), 범위(`1-5`), 콤마 목록(`0,6`), 그 조합.
    """
    if dow_field == "*":
        return True
    for token in dow_field.split(","):
        token = token.strip()
        if "-" in token:
            lo_s, hi_s = token.split("-", 1)
            if lo_s.isdigit() and hi_s.isdigit():
                lo, hi = int(lo_s), int(hi_s)
                if lo <= weekday_cron <= hi:
                    return True
        elif token.isdigit():
            if int(token) == weekday_cron:
                return True
    return False


def _cron_weekday(now: datetime) -> int:
    """datetime → cron 요일(0=일요일 .. 6=토요일).

    Python weekday(): 월=0..일=6. cron: 일=0..토=6. → (weekday()+1) % 7.
    """
    return (now.weekday() + 1) % 7


def _slot(now: datetime, rule_name: str) -> str:
    """de-dup 키 = 날짜(YYYY-MM-DD) + rule_name."""
    return f"{now.strftime('%Y-%m-%d')}_{rule_name}"


def _matches_window(now: datetime, minute: int, hour: int, tick_seconds: int) -> bool:
    """now가 같은 날짜의 (hour:minute) 발화 시각 ± tick_seconds/2 안인지."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    half = tick_seconds / 2
    delta = abs((now - target).total_seconds())
    return delta <= half


def evaluate(
    now: datetime,
    rules: list[TriggerRule] | None = None,
    state: dict | None = None,
    tick_seconds: int = 600,
    toggles: dict | None = None,
) -> list[FiredTrigger]:
    """now 시점에 발화해야 할 트리거 목록 계산. 순수함수(state 미변경).

    Args:
        now: 평가 기준 시각(KST 해석). 항상 주입(테스트 결정성).
        rules: 평가할 룰. None이면 기본 RULES.
        state: de-dup 상태. state["fired"](list[str] slot)에 있는 slot은 재발화 안 함.
        tick_seconds: tick 간격(초). now가 발화 시각 ± tick_seconds/2 안이면 매치.
        toggles: 토글 dict. rule.toggle_key가 여기서 True면 skip.

    Returns:
        발화된 FiredTrigger 목록(state는 건드리지 않음 — 기록은 dispatch가).
    """
    if rules is None:
        rules = RULES
    fired_slots: set[str] = set((state or {}).get("fired", []))
    toggles = toggles or {}

    out: list[FiredTrigger] = []
    for rule in rules:
        if rule.kind != "cron":
            continue
        parsed = _parse_schedule(rule.schedule)
        if parsed is None:
            continue
        minute, hour, dow_field = parsed

        if not _dow_matches(dow_field, _cron_weekday(now)):
            continue
        if not _matches_window(now, minute, hour, tick_seconds):
            continue
        # de-dup: 같은 날짜·룰이면 이미 발화함.
        if _slot(now, rule.name) in fired_slots:
            continue
        # quiet hours: now가 무음 구간 안이면 skip.
        if _in_quiet_hours(now.hour, rule.quiet_hours):
            continue
        # toggle: deep_work 등이 켜져 있으면 skip.
        if rule.toggle_key is not None and toggles.get(rule.toggle_key):
            continue

        out.append(
            FiredTrigger(
                rule_name=rule.name,
                fired_at=now,
                reason=f"cron {rule.schedule} matched @ {now.isoformat()}",
            )
        )
    return out


def _in_quiet_hours(hour: int, quiet: tuple[int, int] | None) -> bool:
    """hour가 quiet_hours[start, end) 안인지. end<start면 자정 횡단 구간."""
    if quiet is None:
        return False
    start, end = quiet
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # 자정 횡단: 예 (22, 7) → [22,24) ∪ [0,7)
    return hour >= start or hour < end


def _coerce_rules(rules: list | None) -> list[TriggerRule] | None:
    """rules 인자가 dict 목록(YAML golden)이면 TriggerRule로 변환. None/TriggerRule은 그대로.

    quiet_hours는 YAML에서 list로 오므로 tuple로 정규화한다.
    """
    if rules is None:
        return None
    out: list[TriggerRule] = []
    for r in rules:
        if isinstance(r, TriggerRule):
            out.append(r)
            continue
        d = dict(r)
        qh = d.get("quiet_hours")
        if isinstance(qh, list) and len(qh) == 2:
            d["quiet_hours"] = (int(qh[0]), int(qh[1]))
        out.append(TriggerRule(**d))
    return out


def evaluate_iso(
    now_iso: str,
    rules: list | None = None,
    state: dict | None = None,
    tick_seconds: int = 600,
    toggles: dict | None = None,
) -> dict:
    """evaluate()의 str 진입점 — golden(kind:call)에서 ISO 시각을 kwargs로 넘기기 위함.

    YAML로는 datetime 객체를 못 넘기므로 ISO 문자열을 받아 datetime으로 파싱한다.
    rules가 dict 목록(YAML)이면 TriggerRule로 coerce해 커스텀 룰도 golden으로 검증 가능.
    반환은 단언 친화적 dict:
        {"n": 발화 수, "names": [rule_name, ...], "reasons": [...]}
    """
    now = datetime.fromisoformat(now_iso)
    coerced = _coerce_rules(rules)
    fired = evaluate(now, rules=coerced, state=state, tick_seconds=tick_seconds, toggles=toggles)
    return {
        "n": len(fired),
        "names": [f.rule_name for f in fired],
        "reasons": [f.reason for f in fired],
    }
