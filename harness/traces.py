"""H3 — Trace query (grep, list, summary).

Replay는 Phase 2로 미룸. 지금은 사후 audit·debug에 쓸 query만.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TraceSummary:
    path: Path
    id: str
    task: str | None
    scope: str | None
    n_events: int
    n_steps_action: int
    n_blocked: int
    finalize_reason: str | None
    cost_tokens: int

    def __str__(self) -> str:
        return (
            f"{self.path.name} · scope={self.scope} · "
            f"steps={self.n_steps_action} blocked={self.n_blocked} "
            f"cost={self.cost_tokens} · {self.finalize_reason} · {self.task!r}"
        )


def _read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize(path: Path) -> TraceSummary:
    """trace JSONL을 TraceSummary로 요약."""
    events = _read_events(path)
    start = next((e for e in events if e["kind"] == "start"), {})
    fin = next((e for e in events if e["kind"] == "finalize"), {})
    return TraceSummary(
        path=path,
        id=path.stem.split("_")[-1],
        task=start.get("task"),
        scope=start.get("scope"),
        n_events=len(events),
        n_steps_action=sum(1 for e in events if e["kind"] == "action"),
        n_blocked=sum(1 for e in events if e["kind"] == "blocked"),
        finalize_reason=fin.get("reason"),
        cost_tokens=fin.get("cost", 0),
    )


def list_traces(
    traces_dir: Path,
    last: int | None = None,
    grep: str | None = None,
    task_contains: str | None = None,
    finalize_reason: str | None = None,
) -> list[TraceSummary]:
    """traces_dir 안 trace JSONL을 필터링해서 TraceSummary list 반환.

    - last: 최근 N개
    - grep: trace JSONL 안에 substring 매치
    - task_contains: start event의 task 필드에 substring 포함
    - finalize_reason: finalize 사유 정확 매치
    """
    if not traces_dir.exists():
        return []
    files = sorted(traces_dir.glob("*.jsonl"))
    summaries = [summarize(f) for f in files]

    if grep:
        summaries = [s for s in summaries if grep in s.path.read_text(encoding="utf-8")]
    if task_contains:
        summaries = [s for s in summaries if s.task and task_contains in s.task]
    if finalize_reason:
        summaries = [s for s in summaries if s.finalize_reason == finalize_reason]
    if last:
        summaries = summaries[-last:]
    return summaries


def load_events(path: Path) -> list[dict[str, Any]]:
    """trace의 모든 event를 list로."""
    return _read_events(path)
