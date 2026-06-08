"""Local OS notification integration.

macOS 전용 로컬 배너 알림. 네트워크나 외부 발송이 아니지만 Channel.send 경로에서는
일관되게 R5 PII 게이트를 통과시킨다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

OS_NOTIFY_BODY_MAX = 500
RunnerFn = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _truncate(text: str, limit: int = OS_NOTIFY_BODY_MAX) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"[:limit]
    return text[: limit - 1] + "…"


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603


def send_notification(
    title: str,
    body: str,
    *,
    runner: RunnerFn | None = None,
    platform: str | None = None,
    limit: int = OS_NOTIFY_BODY_MAX,
) -> dict[str, Any]:
    """Show a local macOS notification; non-darwin platforms safely no-op."""
    current_platform = platform or sys.platform
    if current_platform != "darwin":
        return {"ok": False, "unsupported": True, "platform": current_platform}

    clean_title = _truncate(title, limit=120)
    clean_body = _truncate(body, limit=limit)
    cmd = [
        "osascript",
        "-e",
        "display notification "
        f"{json.dumps(clean_body, ensure_ascii=False)} "
        f"with title {json.dumps(clean_title, ensure_ascii=False)}",
    ]
    run = runner or _default_runner
    result = run(cmd)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stderr": result.stderr,
    }


__all__ = ["OS_NOTIFY_BODY_MAX", "RunnerFn", "send_notification"]
