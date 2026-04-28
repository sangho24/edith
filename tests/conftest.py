# ruff: noqa: UP036, UP017
"""Test-time 셋업.

production 코드는 Python 3.12+ 타겟이지만, 일부 CI/sandbox 환경이 3.10일 수 있어서
`datetime.UTC` (3.11+ 추가) 폴백만 깔아둠. 3.11+에선 if 블록이 no-op.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    import datetime as _datetime

    if not hasattr(_datetime, "UTC"):
        _datetime.UTC = _datetime.timezone.utc  # type: ignore[attr-defined]
