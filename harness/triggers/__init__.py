"""F27 컨텍스트 트리거 v1 — 스케줄러가 부르는 시간 기반 발화 엔진.

PRD docs/08 §4.3. Edith가 사용자에게 먼저 말을 거는 proactive 동작의 토대.
v1은 cron(일일/요일) 기반 트리거만 지원한다. 이벤트 기반(메일 도착 등)은 후속.

설계 원칙:
- evaluate()는 **순수함수** — now·rules·state를 받아 발화 목록만 계산한다.
  시각은 항상 인자로 주입(datetime.now() 직접 호출 금지) → 테스트 결정성.
- 트리거는 LLM tool이 아니다. 스케줄러(외부 tick)가 evaluate→dispatch를 호출한다.
- dispatch()는 실제 Channel.send를 호출하지 않는다(주입형). PII 게이트(F24)·push
  정책(R5/R6) wiring은 별도 PR. 여기서는 발화 판정·de-dup·콜백 dict 생성까지만.
"""

from __future__ import annotations

from harness.triggers.dispatch import dispatch, load_state, save_state
from harness.triggers.evaluator import evaluate, evaluate_iso
from harness.triggers.rules import RULES, FiredTrigger, TriggerRule

__all__ = [
    "RULES",
    "FiredTrigger",
    "TriggerRule",
    "dispatch",
    "evaluate",
    "evaluate_iso",
    "load_state",
    "save_state",
]
