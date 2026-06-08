"""T3.2 — recurring task pattern mining."""

from __future__ import annotations

import json
from pathlib import Path

from harness.patterns import (
    jaccard,
    list_patterns,
    load_trace_tasks,
    match_pattern,
    mine_patterns,
    pattern_summary,
    task_tokens,
)
from harness.state import Context, Trace
from harness.tools.patterns import _pattern_list, _pattern_match


def _trace(path: Path, task: str, scope: str = "personal") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"t": 0.0, "kind": "start", "task": task, "scope": scope}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def test_task_tokens_and_jaccard() -> None:
    a = task_tokens("Daily standup notes")
    b = task_tokens("daily standup notes please")
    assert "daily" in a
    assert jaccard(a, b) == 0.75


def test_mine_patterns_identical_three_support_suggest() -> None:
    traces = [
        {"task": "daily standup notes", "at": "2026-06-01T09:00:00+09:00"},
        {"task": "daily standup notes", "at": "2026-06-02T09:00:00+09:00"},
        {"task": "daily standup notes", "at": "2026-06-03T09:00:00+09:00"},
    ]
    patterns = mine_patterns(traces)
    assert len(patterns) == 1
    assert patterns[0].label == "daily standup notes"
    assert patterns[0].support == 3
    assert patterns[0].level == "suggest"
    assert patterns[0].is_time_regular is True
    assert patterns[0].suggested_cron == "0 9 * * *"


def test_mine_patterns_jaccard_below_threshold_splits() -> None:
    summary = pattern_summary(
        [
            {"task": "draft iclr review"},
            {"task": "book dentist appointment"},
            {"task": "pay rent invoice"},
        ]
    )
    assert summary["n"] == 3
    assert summary["supports"] == [1, 1, 1]
    assert summary["levels"] == ["observe", "observe", "observe"]


def test_load_trace_tasks_and_list_patterns(tmp_path: Path) -> None:
    traces_dir = tmp_path / "harness" / "traces"
    for i in range(3):
        _trace(traces_dir / f"2026-06-0{i + 1}T09-00-00_{i}.jsonl", "daily standup notes")

    loaded = load_trace_tasks(traces_dir)
    assert [t["task"] for t in loaded] == ["daily standup notes"] * 3
    patterns = list_patterns(tmp_path)
    assert len(patterns) == 1
    assert patterns[0].support == 3


def test_match_pattern_returns_best_match() -> None:
    traces = [{"task": "daily standup notes"}] * 3
    out = match_pattern("daily standup notes please", traces)
    assert out["matched"] is True
    assert out["pattern"]["support"] == 3


def test_pattern_tools_are_read_only(tmp_path: Path) -> None:
    traces_dir = tmp_path / "harness" / "traces"
    for i in range(3):
        _trace(traces_dir / f"2026-06-0{i + 1}T09-00-00_{i}.jsonl", "daily standup notes")
    ctx = Context(edith_home=tmp_path, scope="personal", trace=Trace.start("t"))

    listed = _pattern_list({}, ctx)
    matched = _pattern_match({"task": "daily standup notes"}, ctx)

    assert listed["n"] == 1
    assert matched["matched"] is True
    assert not (tmp_path / "harness" / "approvals.json").exists()
