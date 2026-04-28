"""Tool registry + base class.

9개 typed tool을 등록하는 build_default_registry() 진입점 제공.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from harness.state import Context

ToolFn = Callable[[dict[str, Any], Context], Any]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: ToolFn

    def to_anthropic_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def all_specs(self) -> list[dict[str, Any]]:
        return [t.to_anthropic_spec() for t in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any], ctx: Context) -> Any:
        return self.get(name).fn(args, ctx)


def build_default_registry() -> Registry:
    """11개 typed tool 등록 (Phase 1: 9 + Phase 3 F2/F3: 2)."""
    from harness.tools import calendar, mail, raw, util, wiki

    reg = Registry()
    # Phase 1
    reg.register(wiki.WIKI_READ)
    reg.register(wiki.WIKI_WRITE)
    reg.register(wiki.WIKI_SEARCH)
    reg.register(raw.RAW_READ)
    reg.register(raw.RAW_LIST)
    reg.register(raw.CAPTURE_TEXT)
    reg.register(util.QUERY_DB)
    reg.register(util.REQUEST_APPROVAL)
    reg.register(util.EMIT_LOG)
    # Phase 3 F2/F3
    reg.register(calendar.CALENDAR_TODAY)
    reg.register(mail.MAIL_TRIAGE)
    return reg
