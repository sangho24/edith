"""Core dataclasses: Task, Action, Observation, Event, Trace, Budget, Context."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

Scope = Literal["personal", "school", "work", "mixed"]
EventKind = Literal["start", "llm_call", "action", "observation", "blocked", "finalize", "error"]


@dataclass
class Budget:
    """run() 종료 조건. 어느 하나라도 초과하면 즉시 break."""

    max_tokens: int = 8000
    max_steps: int = 20
    max_seconds: float = 60.0


@dataclass
class Action:
    """LLM이 호출하기로 한 tool 액션."""

    tool: str
    args: dict[str, Any]
    tool_use_id: str | None = None


@dataclass
class Observation:
    """tool 실행 결과."""

    tool: str
    result: Any
    is_error: bool = False
    latency_ms: float = 0.0


@dataclass
class Event:
    """trace에 기록되는 단일 이벤트."""

    t: float  # 시작 후 경과 초
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    """한 run의 전체 기록. JSONL로 직렬화."""

    id: str
    task: str
    scope: Scope
    started_at: datetime
    cost_tokens: int = 0
    n_steps: int = 0
    events: list[Event] = field(default_factory=list)
    output: str | None = None
    finalize_reason: str | None = None  # "end_turn" | "budget_*" | "error" | "policy"

    @classmethod
    def start(cls, task: str, scope: Scope = "personal") -> Trace:
        now = datetime.now(UTC)
        tr = cls(id=str(uuid4())[:12], task=task, scope=scope, started_at=now)
        tr.events.append(Event(t=0.0, kind="start", payload={"task": task, "scope": scope}))
        return tr

    def record(self, kind: EventKind, **payload: Any) -> None:
        elapsed = (datetime.now(UTC) - self.started_at).total_seconds()
        self.events.append(Event(t=elapsed, kind=kind, payload=payload))

    def is_done(self) -> bool:
        return self.finalize_reason is not None

    def to_jsonl(self) -> str:
        lines = []
        for ev in self.events:
            d = {"t": round(ev.t, 3), "kind": ev.kind, **ev.payload}
            lines.append(json.dumps(d, ensure_ascii=False, default=str))
        return "\n".join(lines) + "\n"

    def save(self, traces_dir: Path) -> Path:
        traces_dir.mkdir(parents=True, exist_ok=True)
        ts = self.started_at.strftime("%Y-%m-%dT%H-%M-%S")
        path = traces_dir / f"{ts}_{self.id}.jsonl"
        path.write_text(self.to_jsonl(), encoding="utf-8")
        return path


@dataclass
class Context:
    """runtime이 tool에 넘기는 실행 컨텍스트."""

    edith_home: Path
    scope: Scope
    trace: Trace
