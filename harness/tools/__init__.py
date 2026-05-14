"""Tool registry + base class.

Tool·Registry 정의. tool을 skill 단위로 묶어 등록하는 진입점은
harness/skills/ 로 이동했고, build_default_registry()는 그쪽으로 위임한다.
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
    """17개 typed tool 등록 — harness.skills.build_registry()로 위임.

    tool은 이제 harness/skills/<name>.py의 Skill manifest로 묶여 등록된다.
    이 함수는 runtime/cli 호출부 하위호환을 위해 유지.
    """
    from harness.skills import build_registry

    return build_registry()
