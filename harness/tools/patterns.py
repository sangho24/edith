"""pattern_match / pattern_list tools."""

from __future__ import annotations

from typing import Any

from harness.patterns import list_patterns, load_trace_tasks, match_pattern
from harness.state import Context
from harness.tools import Tool


def _pattern_list(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    min_support = args.get("min_support", 1)
    if not isinstance(min_support, int) or isinstance(min_support, bool) or min_support < 1:
        min_support = 1
    patterns = list_patterns(ctx.edith_home, min_support=min_support)
    return {"n": len(patterns), "patterns": [p.to_dict() for p in patterns]}


def _pattern_match(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    task = args.get("task", "")
    if not isinstance(task, str) or not task.strip():
        return {"matched": False, "error": "task must be a non-empty string"}
    traces = load_trace_tasks(ctx.edith_home / "harness" / "traces")
    return match_pattern(task, traces)


PATTERN_LIST = Tool(
    name="pattern_list",
    description="반복 task 패턴을 trace에서 읽어 나열한다. 읽기 전용이며 자동 실행하지 않는다.",
    input_schema={
        "type": "object",
        "properties": {"min_support": {"type": "integer", "default": 1}},
    },
    fn=_pattern_list,
)

PATTERN_MATCH = Tool(
    name="pattern_match",
    description="현재 task가 반복 패턴과 닮았는지 확인한다. 읽기 전용이며 자동 실행하지 않는다.",
    input_schema={
        "type": "object",
        "properties": {"task": {"type": "string"}},
        "required": ["task"],
    },
    fn=_pattern_match,
)
