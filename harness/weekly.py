"""Phase 3 F10 — Weekly Synthesis.

지난 7일치 trace + compile_log를 합성해서 weekly retro 만든다:
- 7일간 task 통계 (n_runs, n_errors, top tools, finalize_reasons)
- 7일간 compile 통계 (새 wiki 페이지, 새 raw, contradictions)
- 7일간 cost 추이
- top entities (wiki 변경 빈도)

매주 일요일 21시 (cron) 실행 → 이메일/카톡 push 또는 wiki/log.md append.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harness.dashboard import _parse_started_at
from harness.traces import load_events


@dataclass
class WeeklySynthesis:
    week_start: str  # YYYY-MM-DD
    week_end: str
    n_runs: int = 0
    n_errors: int = 0
    n_policy_blocks: int = 0
    total_cost_tokens: int = 0
    avg_cost_per_run: float = 0.0
    tool_counts: Counter[str] = field(default_factory=Counter)
    finalize_counts: Counter[str] = field(default_factory=Counter)
    error_messages: list[str] = field(default_factory=list)
    new_wiki_pages: int = 0
    new_raw_files: int = 0
    contradictions_count: int = 0
    compile_runs: int = 0

    def render_text(self) -> str:
        lines = [
            "─" * 60,
            f"☀️ Edith Weekly Synthesis · {self.week_start} ~ {self.week_end}",
            "─" * 60,
            "",
            "📊 활동 통계",
            f"  · runs        : {self.n_runs}",
            f"  · errors      : {self.n_errors}",
            f"  · blocks      : {self.n_policy_blocks}",
            f"  · cost        : {self.total_cost_tokens} tok (avg {self.avg_cost_per_run:.0f}/run)",
            "",
        ]

        if self.tool_counts:
            lines.append("🔧 Top tools (이번 주)")
            for name, n in self.tool_counts.most_common(5):
                lines.append(f"  · {name:<22} : {n:>3}")
            lines.append("")

        if self.finalize_counts:
            lines.append("🏁 Finalize reasons")
            for name, n in self.finalize_counts.most_common(5):
                lines.append(f"  · {name:<22} : {n:>3}")
            lines.append("")

        lines.append("📚 Knowledge")
        lines.append(f"  · 새 wiki 페이지       : {self.new_wiki_pages}")
        lines.append(f"  · 새 raw 파일          : {self.new_raw_files}")
        lines.append(f"  · contradictions      : {self.contradictions_count}")
        lines.append(f"  · compile runs        : {self.compile_runs}")
        lines.append("")

        if self.error_messages:
            lines.append("⚠️ 최근 errors (최대 5)")
            for msg in self.error_messages[-5:]:
                lines.append(f"  · {msg[:80]}")

        return "\n".join(lines)


def _aggregate_traces(traces_dir: Path, cutoff: datetime) -> dict:
    out = {
        "n_runs": 0,
        "n_errors": 0,
        "n_policy_blocks": 0,
        "total_cost": 0,
        "tool_counts": Counter(),
        "finalize_counts": Counter(),
        "error_messages": [],
        "compile_runs": 0,
    }
    if not traces_dir.exists():
        return out
    for path in sorted(traces_dir.glob("*.jsonl")):
        if _parse_started_at(path) < cutoff:
            continue
        events = load_events(path)
        out["n_runs"] += 1
        for ev in events:
            kind = ev.get("kind")
            if kind == "action":
                out["tool_counts"][ev.get("tool", "?")] += 1
            elif kind == "blocked":
                out["n_policy_blocks"] += 1
            elif kind == "error":
                out["n_errors"] += 1
                msg = ev.get("msg", "")
                if msg:
                    out["error_messages"].append(msg)
            elif kind == "finalize":
                reason = ev.get("reason", "?")
                out["finalize_counts"][reason] += 1
                out["total_cost"] += int(ev.get("cost", 0))
            elif kind == "start":
                if "compile" in ev.get("task", "").lower():
                    out["compile_runs"] += 1
    return out


def _aggregate_compile_log(edith_home: Path, cutoff: datetime) -> tuple[int, int]:
    """returns (new_compiled, total_compiled). cutoff 이후 컴파일된 raw 파일 수."""
    log_path = edith_home / "harness" / "compile_log.json"
    if not log_path.exists():
        return 0, 0
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0, 0
    new = 0
    for _rel, info in data.items():
        compiled_at = info.get("compiled_at")
        if not compiled_at:
            continue
        try:
            ts = datetime.fromisoformat(compiled_at)
        except ValueError:
            continue
        if ts >= cutoff:
            new += 1
    return new, len(data)


def _count_recent_files(directory: Path, cutoff: datetime, glob: str = "*.md") -> int:
    """mtime 기준 cutoff 이후 수정된 파일 수."""
    if not directory.exists():
        return 0
    n = 0
    for p in directory.rglob(glob):
        if not p.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        if mtime >= cutoff:
            n += 1
    return n


def _count_contradictions(edith_home: Path) -> int:
    p = edith_home / "wiki" / "contradictions.md"
    if not p.exists():
        return 0
    text = p.read_text(encoding="utf-8")
    # `## YYYY-MM-DD` 헤더 카운트 = 모순 entry 수
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def compose_weekly(edith_home: Path, days: int = 7) -> WeeklySynthesis:
    """지난 N일 (default 7) 치 통계 합성."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    syn = WeeklySynthesis(
        week_start=cutoff.date().isoformat(),
        week_end=now.date().isoformat(),
    )

    trace_agg = _aggregate_traces(edith_home / "harness" / "traces", cutoff)
    syn.n_runs = trace_agg["n_runs"]
    syn.n_errors = trace_agg["n_errors"]
    syn.n_policy_blocks = trace_agg["n_policy_blocks"]
    syn.total_cost_tokens = trace_agg["total_cost"]
    syn.tool_counts = trace_agg["tool_counts"]
    syn.finalize_counts = trace_agg["finalize_counts"]
    syn.error_messages = trace_agg["error_messages"]
    syn.compile_runs = trace_agg["compile_runs"]
    syn.avg_cost_per_run = syn.total_cost_tokens / syn.n_runs if syn.n_runs else 0.0

    new_compiled, _total = _aggregate_compile_log(edith_home, cutoff)
    syn.new_raw_files = new_compiled

    # wiki 새 페이지 — wiki/{entities,concepts,summaries}/*.md mtime
    wiki_count = 0
    for sub in ("entities", "concepts", "summaries"):
        wiki_count += _count_recent_files(edith_home / "wiki" / sub, cutoff)
    syn.new_wiki_pages = wiki_count

    syn.contradictions_count = _count_contradictions(edith_home)

    return syn
