"""Edith의 '오늘' 기준 시간대.

Edith는 단일 사용자(상호님, 한국)의 Knowledge Twin이므로 '오늘'은 **사용자 로컬 day**다.
그런데 스케줄러·서버는 now를 UTC로 넘기고(예: datetime.now(UTC)), 데이터(일정·헬스·시드)는
KST(+09:00)로 stamp된다. now를 그대로 .date() 하면 자정 부근에 UTC 날짜와 KST 날짜가 달라져
그날 일정/헬스가 창 밖으로 빠진다(리뷰에서 confirmed critical).

그래서 '오늘'은 항상 **Edith 시간대(기본 KST)** 로 계산한다. now가 UTC든 KST든 시스템 로컬이든
무관하게 결정적이다(시스템 tz에 의존하지 않음 → CI에서도 동일). KST는 DST가 없어 고정 offset이
정확하다. 다른 지역 사용자는 EDITH_TZ_OFFSET_HOURS로 덮어쓴다.

주의: compose_brief의 now=None 경로는 기존 호환(UTC 창/ date.today())을 위해 이 모듈을 쓰지
않는다. now가 명시될 때(데모·체크인·서버 brief)만 Edith 시간대 기준으로 통일한다.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

# 기본 KST(+09:00). 환경변수로 override (예: EDITH_TZ_OFFSET_HOURS=-5).
_DEFAULT_OFFSET_HOURS = 9.0


def edith_tz() -> timezone:
    """Edith의 기준 시간대(기본 KST). EDITH_TZ_OFFSET_HOURS로 변경 가능."""
    raw = os.environ.get("EDITH_TZ_OFFSET_HOURS")
    try:
        hours = float(raw) if raw is not None else _DEFAULT_OFFSET_HOURS
    except ValueError:
        hours = _DEFAULT_OFFSET_HOURS
    return timezone(timedelta(hours=hours))


def edith_now() -> datetime:
    """Edith 시간대 기준 현재 시각(aware)."""
    return datetime.now(edith_tz())


def edith_today(ref: datetime) -> date:
    """ref 순간을 Edith 시간대로 변환한 날짜. naive면 이미 Edith 시간대로 간주."""
    tz = edith_tz()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=tz)
    return ref.astimezone(tz).date()


__all__ = ["edith_now", "edith_today", "edith_tz"]
