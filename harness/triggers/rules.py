"""F27 트리거 룰 선언 — TriggerRule / FiredTrigger dataclass + v1 기본 RULES.

cron 시각은 **KST 기준**으로 표기한다. evaluate()가 받는 now도 KST로 해석되므로
요일·시각 매칭이 일관된다(GitHub Actions의 UTC cron과 헷갈리지 말 것).

cron 필드 순서는 표준 5필드: `분 시 일 월 요일`.
요일: 0=일요일 ... 6=토요일. `1-5`=월~금. `*`=매일.
v1은 분/시가 숫자이고 일·월이 `*`인 cron만 안정 처리한다(rules는 모두 그 형태).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TriggerRule:
    """단일 트리거 정의.

    Attributes:
        name: 룰 식별자(slot de-dup·toggle 조회 키로도 쓰임).
        kind: v1은 "cron"만. (이벤트 기반은 후속에서 다른 kind로 확장.)
        schedule: cron 표현식(KST 기준, `분 시 일 월 요일`).
        action: 발화 시 수행할 액션 이름(dispatch가 콜백 dict로 변환).
        channel: 출력 채널 이름("telegram" 등). 실제 send는 dispatch가 안 함.
        scope: 이 트리거가 동작하는 scope.
        quiet_hours: (start_hour, end_hour) — 이 시간대[start, end) 안이면 skip.
            야간 무음. end < start이면 자정을 가로지르는 구간(예: (22, 7)).
            None이면 무음 없음.
        toggle_key: toggles dict에서 조회할 키. True면 skip(예: deep_work 중 무음).
            None이면 toggle 영향 없음.
        max_per_month: 월 최대 발화 횟수(예산 가드). None이면 무제한.
    """

    name: str
    kind: str  # Literal["cron"] — v1
    schedule: str
    action: str
    channel: str
    scope: str
    quiet_hours: tuple[int, int] | None = None
    toggle_key: str | None = None
    max_per_month: int | None = None


@dataclass(frozen=True)
class FiredTrigger:
    """발화 결과 한 건."""

    rule_name: str
    fired_at: datetime
    reason: str


# v1 기본 룰 3종. 모두 cron-only, KST 기준.
RULES: list[TriggerRule] = [
    TriggerRule(
        name="morning_brief",
        kind="cron",
        schedule="0 8 * * 1-5",  # 평일(월~금) 08:00 KST
        action="compose_brief",
        channel="telegram",
        scope="personal",
        quiet_hours=None,
        toggle_key="deep_work",
        max_per_month=23,
    ),
    TriggerRule(
        name="eod_checkin",
        kind="cron",
        schedule="0 21 * * *",  # 매일 21:00 KST
        action="eod_checkin",
        channel="telegram",
        scope="personal",
        quiet_hours=None,
        toggle_key="deep_work",
        max_per_month=31,
    ),
    TriggerRule(
        name="weekly_synth",
        kind="cron",
        schedule="0 22 * * 0",  # 일요일 22:00 KST
        action="weekly_synth",
        channel="telegram",
        scope="personal",
        quiet_hours=None,
        toggle_key=None,
        max_per_month=5,
    ),
]
