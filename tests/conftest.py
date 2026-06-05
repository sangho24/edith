# ruff: noqa: UP036, UP017
"""Test-time 셋업.

production 코드는 Python 3.12+ 타겟이지만, 일부 CI/sandbox 환경이 3.10일 수 있어서
`datetime.UTC` (3.11+ 추가) 폴백만 깔아둠. 3.11+에선 if 블록이 no-op.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info < (3, 11):
    import datetime as _datetime

    if not hasattr(_datetime, "UTC"):
        _datetime.UTC = _datetime.timezone.utc  # type: ignore[attr-defined]


# `uv run`이 .env를 자동 로드하므로, 사용자가 실사용을 위해 .env에 넣은
# EDITH_MAIL_BACKEND=gmail / EDITH_CALENDAR_BACKEND=google 등이 테스트 프로세스로 새어든다.
# 그러면 compose_brief·select_mail_source가 실제 Gmail/Calendar API를 때려(분 단위·실데이터
# 의존) 단위 테스트가 깨진다. 아래 autouse fixture가 매 테스트 시작 시 이 소스 스위치를
# 제거한다(monkeypatch라 자동 복원). 실연동을 검증할 테스트는 본문에서 monkeypatch.setenv로
# 직접 켠다(autouse보다 나중 실행 → 우선).
_REAL_SOURCE_ENV = (
    "EDITH_MAIL_BACKEND",
    "EDITH_CALENDAR_BACKEND",
    "EDITH_HEALTH_EXPORT",
    "EDITH_DS_DIGEST_URL",
    "EDITH_DS_DIGEST_LATEST",
)


@pytest.fixture(autouse=True)
def _isolate_real_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _REAL_SOURCE_ENV:
        monkeypatch.delenv(key, raising=False)
