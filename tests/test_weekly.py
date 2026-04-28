"""Phase 3 F10 — Weekly synthesis tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from harness.weekly import compose_weekly


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "wiki" / "entities").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


def _write_trace(home: Path, ts: datetime, events: list[dict]) -> None:
    name = f"{ts.strftime('%Y-%m-%dT%H-%M-%S')}_{events[0].get('task', 'x')[:6]}.jsonl"
    p = home / "harness" / "traces" / name
    p.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
        encoding="utf-8",
    )


def test_empty_week(edith_home: Path) -> None:
    syn = compose_weekly(edith_home)
    assert syn.n_runs == 0
    assert syn.total_cost_tokens == 0


def test_aggregates_recent_traces(edith_home: Path) -> None:
    now = datetime.now(UTC)
    _write_trace(
        edith_home,
        now - timedelta(hours=2),
        [
            {"t": 0.0, "kind": "start", "task": "abc"},
            {"t": 1.0, "kind": "action", "tool": "wiki_search"},
            {"t": 2.0, "kind": "finalize", "reason": "end_turn", "cost": 500},
        ],
    )
    _write_trace(
        edith_home,
        now - timedelta(hours=10),
        [
            {"t": 0.0, "kind": "start", "task": "def"},
            {"t": 1.0, "kind": "action", "tool": "wiki_read"},
            {"t": 2.0, "kind": "error", "where": "tool", "msg": "boom"},
            {"t": 3.0, "kind": "finalize", "reason": "error", "cost": 200},
        ],
    )
    syn = compose_weekly(edith_home, days=7)
    assert syn.n_runs == 2
    assert syn.n_errors == 1
    assert syn.total_cost_tokens == 700
    assert syn.tool_counts["wiki_search"] == 1
    assert syn.tool_counts["wiki_read"] == 1


def test_excludes_old_traces(edith_home: Path) -> None:
    """8일 전 trace는 7일 window 밖 → 미포함."""
    old = datetime.now(UTC) - timedelta(days=8)
    _write_trace(
        edith_home,
        old,
        [
            {"t": 0.0, "kind": "start", "task": "old"},
            {"t": 1.0, "kind": "finalize", "reason": "end_turn", "cost": 999},
        ],
    )
    syn = compose_weekly(edith_home, days=7)
    assert syn.n_runs == 0
    assert syn.total_cost_tokens == 0


def test_avg_cost_calculated(edith_home: Path) -> None:
    now = datetime.now(UTC)
    for i, cost in enumerate([100, 200, 300]):
        _write_trace(
            edith_home,
            now - timedelta(hours=i + 1),
            [
                {"t": 0.0, "kind": "start", "task": f"t{i}"},
                {"t": 1.0, "kind": "finalize", "reason": "end_turn", "cost": cost},
            ],
        )
    syn = compose_weekly(edith_home)
    assert syn.total_cost_tokens == 600
    assert syn.n_runs == 3
    assert abs(syn.avg_cost_per_run - 200.0) < 0.1


def test_compile_log_aggregation(edith_home: Path) -> None:
    log = {
        "raw/x.md": {"compiled_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()},
        "raw/y.md": {"compiled_at": (datetime.now(UTC) - timedelta(days=10)).isoformat()},
        "raw/z.md": {"compiled_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat()},
    }
    (edith_home / "harness" / "compile_log.json").write_text(json.dumps(log), encoding="utf-8")
    syn = compose_weekly(edith_home, days=7)
    # 7일 안: x, z (2개)
    assert syn.new_raw_files == 2


def test_contradictions_count(edith_home: Path) -> None:
    (edith_home / "wiki" / "contradictions.md").write_text(
        """# Contradictions

## 2026-04-25 — entities/x.md
- 기존 vs 새

## 2026-04-26 — entities/y.md
- 기존 vs 새
""",
        encoding="utf-8",
    )
    syn = compose_weekly(edith_home)
    assert syn.contradictions_count == 2


def test_render_text_includes_sections(edith_home: Path) -> None:
    syn = compose_weekly(edith_home)
    text = syn.render_text()
    assert "Edith Weekly Synthesis" in text
    assert "활동 통계" in text
    assert "Knowledge" in text


def test_error_messages_collected(edith_home: Path) -> None:
    now = datetime.now(UTC)
    _write_trace(
        edith_home,
        now - timedelta(hours=1),
        [
            {"t": 0.0, "kind": "start", "task": "x"},
            {"t": 1.0, "kind": "error", "where": "tool:wiki_write", "msg": "support_refs required"},
            {"t": 2.0, "kind": "finalize", "reason": "error"},
        ],
    )
    syn = compose_weekly(edith_home)
    assert "support_refs required" in syn.error_messages
