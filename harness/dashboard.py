"""H6 — Observability dashboard.

최근 N시간 window의 trace 통계 (runs, errors, policy blocks, cost, top tools).
weekly report (cron 자동)는 Phase 2 cycle에서 추가.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harness.traces import load_events


def _parse_started_at(path: Path) -> datetime:
    """trace 파일명 'YYYY-MM-DDTHH-MM-SS_id.jsonl' 에서 시작 시각 파싱."""
    name = path.stem
    ts_part = name.rsplit("_", 1)[0]
    try:
        return datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


@dataclass
class DashboardStats:
    window_hours: int
    n_runs: int = 0
    n_errors: int = 0
    n_policy_blocks: int = 0
    total_cost_tokens: int = 0
    finalize_counts: Counter[str] = field(default_factory=Counter)
    tool_counts: Counter[str] = field(default_factory=Counter)
    recent_errors: list[dict] = field(default_factory=list)

    @property
    def avg_cost_tokens(self) -> float:
        return self.total_cost_tokens / self.n_runs if self.n_runs else 0.0

    def render_text(self) -> str:
        lines = [
            "─" * 50,
            f"Edith dashboard · {self.window_hours}h window ({self.n_runs} runs)",
            "─" * 50,
            f"errors        : {self.n_errors}",
            f"policy_blocks : {self.n_policy_blocks}",
            f"total cost    : {self.total_cost_tokens} tokens",
            f"avg cost      : {self.avg_cost_tokens:.0f} tokens / run",
        ]
        if self.tool_counts:
            lines.append("")
            lines.append("Top tools:")
            for name, n in self.tool_counts.most_common(5):
                lines.append(f"  {name:<16} : {n:>3}")
        if self.finalize_counts:
            lines.append("")
            lines.append("finalize reasons:")
            for name, n in self.finalize_counts.most_common(5):
                lines.append(f"  {name:<16} : {n:>3}")
        if self.recent_errors:
            lines.append("")
            lines.append("Recent errors (last 5):")
            for err in self.recent_errors[-5:]:
                where = err.get("where", "?")
                msg = err.get("msg", "")
                lines.append(f"  {where}: {msg[:80]}")
        return "\n".join(lines)


def compute_stats(traces_dir: Path, window_hours: int = 24) -> DashboardStats:
    """traces_dir 안 trace 파일을 window 안에서 집계."""
    stats = DashboardStats(window_hours=window_hours)
    if not traces_dir.exists():
        return stats

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    for path in sorted(traces_dir.glob("*.jsonl")):
        if _parse_started_at(path) < cutoff:
            continue
        events = load_events(path)
        stats.n_runs += 1
        for ev in events:
            kind = ev.get("kind")
            if kind == "action":
                stats.tool_counts[ev.get("tool", "?")] += 1
            elif kind == "blocked":
                stats.n_policy_blocks += 1
            elif kind == "error":
                stats.n_errors += 1
                stats.recent_errors.append(ev)
            elif kind == "finalize":
                stats.finalize_counts[ev.get("reason", "?")] += 1
                stats.total_cost_tokens += int(ev.get("cost", 0))

    return stats
