"""F27 트리거 디스패치 — 발화된 트리거를 처리하고 de-dup 상태를 기록.

dispatch()는 실제 Channel.send를 호출하지 않는다(주입형으로 남김).
발화별 콜백 dict(action·channel·scope·slot)를 만들고, state["fired"]에 slot을
추가해 같은 날짜·룰의 재발화를 막는다. PII 게이트(F24)·push 정책(R5/R6) wiring은
스케줄러/후속 PR에서 이 콜백 dict를 받아 수행한다.

trigger_state.json: edith_home/harness/trigger_state.json. {"fired": [slot, ...]}.
"""

from __future__ import annotations

from pathlib import Path

from harness.storage import atomic_write_json, read_json_file
from harness.triggers.rules import RULES, FiredTrigger, TriggerRule


def _state_path(edith_home: Path) -> Path:
    """trigger_state.json 경로."""
    return edith_home / "harness" / "trigger_state.json"


def load_state(edith_home: Path) -> dict:
    """trigger_state.json 로드. 없으면 빈 상태({"fired": []})."""
    path = _state_path(edith_home)
    data = read_json_file(path, {"fired": []})
    if not isinstance(data, dict):
        return {"fired": []}
    data.setdefault("fired", [])
    return data


def save_state(edith_home: Path, state: dict) -> Path:
    """state를 trigger_state.json에 기록. 경로 반환."""
    path = _state_path(edith_home)
    atomic_write_json(path, state)
    return path


def _slot(fired: FiredTrigger) -> str:
    """발화의 de-dup slot = 날짜 + rule_name (evaluator._slot과 동일 규약)."""
    return f"{fired.fired_at.strftime('%Y-%m-%d')}_{fired.rule_name}"


def _rule_index(rules: list[TriggerRule]) -> dict[str, TriggerRule]:
    return {r.name: r for r in rules}


def dispatch(
    fired: list[FiredTrigger],
    state: dict,
    rules: list[TriggerRule] | None = None,
) -> dict:
    """발화된 트리거를 처리. 콜백 dict 반환 + state["fired"]에 slot 기록(de-dup).

    실제 발송은 하지 않는다 — 발화별 콜백 명세(action·channel·scope·slot)를 만들어
    스케줄러/후속 PR이 PII 게이트(F24)·push 정책을 적용해 실행하도록 넘긴다.
    이미 slot이 기록된 발화는 중복으로 보고 skip(멱등).

    Args:
        fired: evaluate()가 돌려준 발화 목록.
        state: de-dup 상태(in-place로 state["fired"]에 slot 추가).
        rules: 룰 인덱스(action/channel/scope 조회용). None이면 기본 RULES.

    Returns:
        {"callbacks": [{rule_name, action, channel, scope, slot, fired_at}, ...],
         "fired_slots": [...신규 기록된 slot...],
         "skipped": [...이미 기록돼 중복인 slot...]}
    """
    if rules is None:
        rules = RULES
    by_name = _rule_index(rules)
    state.setdefault("fired", [])
    already: set[str] = set(state["fired"])

    callbacks: list[dict] = []
    new_slots: list[str] = []
    skipped: list[str] = []

    for ft in fired:
        slot = _slot(ft)
        if slot in already:
            skipped.append(slot)
            continue
        rule = by_name.get(ft.rule_name)
        callbacks.append(
            {
                "rule_name": ft.rule_name,
                "action": rule.action if rule else None,
                "channel": rule.channel if rule else None,
                "scope": rule.scope if rule else None,
                "slot": slot,
                "fired_at": ft.fired_at.isoformat(),
                "reason": ft.reason,
            }
        )
        state["fired"].append(slot)
        already.add(slot)
        new_slots.append(slot)

    return {"callbacks": callbacks, "fired_slots": new_slots, "skipped": skipped}
