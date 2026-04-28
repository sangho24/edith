"""H3 trace query — list, grep, filter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.traces import list_traces, load_events, summarize


@pytest.fixture
def traces_dir(tmp_path: Path) -> Path:
    """3개 mock trace 생성."""
    d = tmp_path / "traces"
    d.mkdir()

    def _write(name: str, events: list[dict]) -> Path:
        p = d / name
        p.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
            encoding="utf-8",
        )
        return p

    _write(
        "2026-04-28T08-00-00_aaaa.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "morning brief", "scope": "personal"},
            {"t": 1.2, "kind": "action", "tool": "wiki_search"},
            {"t": 2.0, "kind": "finalize", "reason": "end_turn", "cost": 412},
        ],
    )
    _write(
        "2026-04-28T09-00-00_bbbb.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "이메일 분류", "scope": "personal"},
            {"t": 1.0, "kind": "action", "tool": "raw_list"},
            {"t": 2.0, "kind": "blocked", "tool": "gmail_send", "reason": "R2"},
            {"t": 3.0, "kind": "finalize", "reason": "end_turn", "cost": 800},
        ],
    )
    _write(
        "2026-04-28T10-00-00_cccc.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "loop", "scope": "personal"},
            {"t": 1.0, "kind": "action", "tool": "emit_log"},
            {"t": 2.0, "kind": "finalize", "reason": "budget_steps"},
        ],
    )
    return d


def test_list_all(traces_dir: Path) -> None:
    summaries = list_traces(traces_dir)
    assert len(summaries) == 3
    assert summaries[0].task == "morning brief"
    assert summaries[1].task == "이메일 분류"


def test_grep_filter(traces_dir: Path) -> None:
    summaries = list_traces(traces_dir, grep="gmail_send")
    assert len(summaries) == 1
    assert summaries[0].task == "이메일 분류"
    assert summaries[0].n_blocked == 1


def test_task_contains_filter(traces_dir: Path) -> None:
    summaries = list_traces(traces_dir, task_contains="이메일")
    assert len(summaries) == 1
    assert summaries[0].task == "이메일 분류"


def test_finalize_reason_filter(traces_dir: Path) -> None:
    summaries = list_traces(traces_dir, finalize_reason="budget_steps")
    assert len(summaries) == 1
    assert summaries[0].task == "loop"


def test_last_limit(traces_dir: Path) -> None:
    summaries = list_traces(traces_dir, last=2)
    assert len(summaries) == 2
    assert summaries[-1].task == "loop"


def test_summarize_counts(traces_dir: Path) -> None:
    files = sorted(traces_dir.glob("*.jsonl"))
    s = summarize(files[1])  # 이메일 분류
    assert s.n_steps_action == 1
    assert s.n_blocked == 1
    assert s.cost_tokens == 800


def test_load_events_returns_full_list(traces_dir: Path) -> None:
    files = sorted(traces_dir.glob("*.jsonl"))
    events = load_events(files[0])
    assert len(events) == 3
    assert events[0]["kind"] == "start"
    assert events[-1]["kind"] == "finalize"


def test_empty_dir() -> None:
    assert list_traces(Path("/nonexistent")) == []
