"""GitHub Actions workflow YAML 관리.

read: get_crons(path) — schedule.cron list 반환
write: set_cron(path, new_cron, idx) — idx번째 cron line 교체 (preserves comments/formatting)

KST↔UTC 변환 helper 포함 — GitHub Actions cron은 항상 UTC 기준이므로 사용자가 KST 시간을
말하면 (KST 08:00) UTC로 변환 (UTC 23:00 of previous day) 후 cron 작성.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def read_workflow(workflow_path: Path) -> dict:
    """workflow YAML을 dict로 parse."""
    return yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}


def get_crons(workflow_path: Path) -> list[str]:
    """workflow의 schedule.cron list 반환 (없으면 빈 list).

    workflow YAML 예시:
        on:
          schedule:
            - cron: '10 22 * * *'
    → ['10 22 * * *']
    """
    data = read_workflow(workflow_path)
    on = data.get("on") or data.get(True)  # YAML 'on:' 가 boolean True로 parse됨
    if not isinstance(on, dict):
        return []
    schedules = on.get("schedule") or []
    if not isinstance(schedules, list):
        return []
    return [s["cron"] for s in schedules if isinstance(s, dict) and "cron" in s]


def set_cron(workflow_path: Path, new_cron: str, idx: int = 0) -> tuple[bool, str]:
    """idx번째 cron line을 new_cron으로 교체. comment·indent·quoting 보존.

    Returns:
        (ok, message_or_diff)
    """
    if not workflow_path.exists():
        return False, f"workflow not found: {workflow_path}"

    text = workflow_path.read_text(encoding="utf-8")
    # `- cron: '...'` 또는 `- cron: "..."` 또는 quoting 없는 형태 모두 매치
    pattern = re.compile(r"(-\s*cron:\s*)(['\"]?)([^'\"\n]+?)(\2)(\s*(?:#.*)?)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return False, "no cron found in workflow"
    if idx >= len(matches):
        return False, f"cron[{idx}] not found (have {len(matches)} cron line(s))"

    m = matches[idx]
    old_cron = m.group(3)
    quote = m.group(2) or "'"
    replacement = f"{m.group(1)}{quote}{new_cron}{quote}{m.group(5)}"
    new_text = text[: m.start()] + replacement + text[m.end() :]
    workflow_path.write_text(new_text, encoding="utf-8")
    return True, f"cron[{idx}]: '{old_cron}' → '{new_cron}'"


def cron_for_kst_time(hour: int, minute: int = 0) -> str:
    """KST hh:mm → UTC cron expression.

    KST = UTC+9 → KST 08:00 = UTC 23:00 (previous day) = '0 23 * * *'.
    daily 매일 동일 시각이면 day_of_month·month·day_of_week는 모두 *.
    """
    if not (0 <= hour <= 23):
        raise ValueError(f"hour must be 0-23, got {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"minute must be 0-59, got {minute}")
    utc_hour = (hour - 9) % 24
    return f"{minute} {utc_hour} * * *"


def parse_cron_to_kst(cron: str) -> tuple[int, int] | None:
    """단순 daily cron('M H * * *') → KST (hour, minute) tuple. 그 외는 None.

    주의: minute 필드가 *이거나 step이면 None.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        return None
    minute_str, hour_str, dom, mon, dow = parts
    if not (minute_str.isdigit() and hour_str.isdigit()):
        return None
    if (dom, mon, dow) != ("*", "*", "*"):
        return None
    minute = int(minute_str)
    utc_hour = int(hour_str)
    kst_hour = (utc_hour + 9) % 24
    return kst_hour, minute
