"""H6 dashboard — trace 집계 통계."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness.dashboard import compute_stats


@pytest.fixture
def traces_dir(tmp_path: Path) -> Path:
    """최근·오래된 trace 섞어서 4개 생성."""
    d = tmp_path / "traces"
    d.mkdir()

    now = datetime.now(UTC)
    recent_ts = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H-%M-%S")
    older_ts = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H-%M-%S")

    def _write(filename: str, events: list[dict]) -> None:
        (d / filename).write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
            encoding="utf-8",
        )

    # window 안 (recent) — 3개
    _write(
        f"{recent_ts}_aaaa.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "morning brief"},
            {"t": 1.0, "kind": "action", "tool": "wiki_search"},
            {"t": 2.0, "kind": "action", "tool": "wiki_read"},
            {"t": 3.0, "kind": "finalize", "reason": "end_turn", "cost": 412},
        ],
    )
    _write(
        f"{recent_ts[:-1]}1_bbbb.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "이메일 분류"},
            {"t": 1.0, "kind": "action", "tool": "wiki_search"},
            {"t": 2.0, "kind": "blocked", "tool": "gmail_send", "reason": "R2"},
            {"t": 3.0, "kind": "finalize", "reason": "end_turn", "cost": 800},
        ],
    )
    _write(
        f"{recent_ts[:-1]}2_cccc.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "loop"},
            {"t": 1.0, "kind": "action", "tool": "emit_log"},
            {"t": 2.0, "kind": "error", "where": "tool:wiki_write", "msg": "support_refs required"},
            {"t": 3.0, "kind": "finalize", "reason": "budget_steps", "cost": 100},
        ],
    )
    # window 밖 (old) — 1개
    _write(
        f"{older_ts}_dddd.jsonl",
        [
            {"t": 0.0, "kind": "start", "task": "old"},
            {"t": 1.0, "kind": "action", "tool": "raw_list"},
            {"t": 2.0, "kind": "finalize", "reason": "end_turn", "cost": 9999},
        ],
    )
    return d


def test_window_filters_old_traces(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=24)
    assert stats.n_runs == 3  # old 1개 제외


def test_aggregate_counts(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=24)
    assert stats.n_errors == 1
    assert stats.n_policy_blocks == 1
    assert stats.total_cost_tokens == 412 + 800 + 100
    assert stats.tool_counts["wiki_search"] == 2
    assert stats.tool_counts["wiki_read"] == 1
    assert stats.tool_counts["emit_log"] == 1
    assert stats.finalize_counts["end_turn"] == 2
    assert stats.finalize_counts["budget_steps"] == 1


def test_avg_cost(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=24)
    expected = (412 + 800 + 100) / 3
    assert abs(stats.avg_cost_tokens - expected) < 0.1


def test_recent_errors_captured(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=24)
    assert len(stats.recent_errors) == 1
    err = stats.recent_errors[0]
    assert err["where"] == "tool:wiki_write"
    assert "support_refs" in err["msg"]


def test_render_text(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=24)
    text = stats.render_text()
    assert "3 runs" in text
    assert "errors        : 1" in text
    assert "policy_blocks : 1" in text
    assert "wiki_search" in text
    assert "end_turn" in text


def test_empty_dir() -> None:
    stats = compute_stats(Path("/nonexistent_dir_xxx"), window_hours=24)
    assert stats.n_runs == 0
    assert stats.avg_cost_tokens == 0.0
    text = stats.render_text()
    assert "0 runs" in text


def test_wide_window_includes_old(traces_dir: Path) -> None:
    stats = compute_stats(traces_dir, window_hours=72)
    assert stats.n_runs == 4
    assert stats.total_cost_tokens == 412 + 800 + 100 + 9999
