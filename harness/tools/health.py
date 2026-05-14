"""health_summary tool — F15 Apple Health 최근 데이터 read. scope=personal."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from harness.integrations.apple_health import daily_summary, get_health_source
from harness.state import Context
from harness.tools import Tool

_DEFAULT_DAYS = 7


def _health_summary(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    days = int(args.get("days", _DEFAULT_DAYS))
    days = max(1, min(days, 30))

    end = date.today()
    start = end - timedelta(days=days - 1)
    samples = get_health_source(ctx.edith_home).samples(start, end)

    by_day: dict[str, dict[str, float]] = {}
    for offset in range(days):
        d = start + timedelta(days=offset)
        summary = daily_summary(samples, d)
        if summary:
            by_day[d.isoformat()] = summary

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "days_with_data": len(by_day),
        "by_day": by_day,
    }


HEALTH_SUMMARY = Tool(
    name="health_summary",
    description=(
        "최근 N일(기본 7) Apple Health 데이터 요약 read. "
        "걸음·수면·활동에너지·심박. scope=personal, read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "조회 일수 (1-30, 기본 7)"}
        },
    },
    fn=_health_summary,
)
