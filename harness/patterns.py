"""Deterministic recurring task pattern mining.

Patterns are mined from completed trace start tasks only. The miner is deliberately
LLM-free: tokenize task text, greedily cluster by Jaccard similarity, then expose
support and optional time regularity hints.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

PatternLevel = Literal["observe", "suggest"]

JACCARD_THRESHOLD = 0.6
SUGGEST_SUPPORT = 3
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass(frozen=True)
class RecurringPattern:
    label: str
    support: int
    is_time_regular: bool
    suggested_cron: str | None
    level: PatternLevel

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _TaskTrace:
    task: str
    tokens: frozenset[str]
    at: datetime | None
    order: int


def task_tokens(task: str) -> frozenset[str]:
    """Normalize task text into deterministic tokens."""
    return frozenset(tok.lower() for tok in _TOKEN_RE.findall(task) if tok.strip())


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def mine_patterns(
    traces: list[dict[str, Any]],
    *,
    threshold: float = JACCARD_THRESHOLD,
    suggest_support: int = SUGGEST_SUPPORT,
) -> list[RecurringPattern]:
    """Cluster repeated task traces by token Jaccard similarity."""
    tasks = [_task_trace(t, idx) for idx, t in enumerate(traces)]
    tasks = [t for t in tasks if t is not None and t.tokens]
    clusters: list[list[_TaskTrace]] = []
    cluster_tokens: list[frozenset[str]] = []

    for item in tasks:
        best_idx: int | None = None
        best_score = threshold
        for idx, rep_tokens in enumerate(cluster_tokens):
            score = jaccard(item.tokens, rep_tokens)
            if score >= best_score:
                best_idx = idx
                best_score = score
        if best_idx is None:
            clusters.append([item])
            cluster_tokens.append(item.tokens)
        else:
            clusters[best_idx].append(item)
            cluster_tokens[best_idx] = _cluster_fingerprint(clusters[best_idx])

    patterns = [_cluster_to_pattern(c, suggest_support) for c in clusters]
    return sorted(patterns, key=lambda p: (-p.support, p.label))


def pattern_summary(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Golden-friendly summary of mined patterns."""
    patterns = mine_patterns(traces)
    return {
        "n": len(patterns),
        "labels": [p.label for p in patterns],
        "supports": [p.support for p in patterns],
        "levels": [p.level for p in patterns],
    }


def load_trace_tasks(traces_dir: Path) -> list[dict[str, Any]]:
    """Read trace start events from JSONL files into mine_patterns input records."""
    if not traces_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(traces_dir.glob("*.jsonl")):
        started_at = _datetime_from_trace_filename(path.name)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") != "start" or not isinstance(rec.get("task"), str):
                continue
            out.append(
                {
                    "task": rec["task"],
                    "at": rec.get("at") or rec.get("started_at") or started_at,
                    "scope": rec.get("scope"),
                    "path": str(path),
                }
            )
            break
    return out


def list_patterns(edith_home: Path, *, min_support: int = 1) -> list[RecurringPattern]:
    """Mine patterns from edith_home/harness/traces."""
    patterns = mine_patterns(load_trace_tasks(edith_home / "harness" / "traces"))
    return [p for p in patterns if p.support >= min_support]


def match_pattern(
    task: str,
    traces: list[dict[str, Any]],
    *,
    threshold: float = JACCARD_THRESHOLD,
) -> dict[str, Any]:
    """Return the best recurring pattern match for a task, if any."""
    tokens = task_tokens(task)
    best: tuple[RecurringPattern, float] | None = None
    for pattern in mine_patterns(traces, threshold=threshold):
        score = jaccard(tokens, task_tokens(pattern.label))
        if score >= threshold and (best is None or score > best[1]):
            best = (pattern, score)
    if best is None:
        return {"matched": False, "score": 0.0}
    pattern, score = best
    return {"matched": True, "score": round(score, 3), "pattern": pattern.to_dict()}


def suggest_pattern_lines(edith_home: Path, *, limit: int = 1) -> list[str]:
    """Brief/checkin display lines for suggest-level patterns only."""
    lines: list[str] = []
    for pattern in list_patterns(edith_home, min_support=SUGGEST_SUPPORT):
        if pattern.level != "suggest":
            continue
        lines.append(f"🔁 늘 하시던 {pattern.label}")
        if len(lines) >= limit:
            break
    return lines


def _task_trace(trace: dict[str, Any], order: int) -> _TaskTrace | None:
    task = trace.get("task")
    if not isinstance(task, str) or not task.strip():
        return None
    return _TaskTrace(
        task=_normalize_label(task),
        tokens=task_tokens(task),
        at=_parse_dt(trace.get("at") or trace.get("started_at") or trace.get("ts")),
        order=order,
    )


def _cluster_fingerprint(cluster: list[_TaskTrace]) -> frozenset[str]:
    common = set(cluster[0].tokens)
    for item in cluster[1:]:
        common &= set(item.tokens)
    if common:
        return frozenset(common)
    counts: Counter[str] = Counter()
    for item in cluster:
        counts.update(item.tokens)
    top = {tok for tok, _n in counts.most_common(6)}
    return frozenset(top)


def _cluster_to_pattern(cluster: list[_TaskTrace], suggest_support: int) -> RecurringPattern:
    label = _cluster_label(cluster)
    support = len(cluster)
    is_regular, cron = _time_regular(cluster)
    level: PatternLevel = "suggest" if support >= suggest_support else "observe"
    return RecurringPattern(
        label=label,
        support=support,
        is_time_regular=is_regular,
        suggested_cron=cron,
        level=level,
    )


def _cluster_label(cluster: list[_TaskTrace]) -> str:
    counts: Counter[str] = Counter(item.task for item in cluster)
    first_order = {item.task: item.order for item in cluster}
    label, _count = sorted(counts.items(), key=lambda kv: (-kv[1], first_order[kv[0]]))[0]
    return label


def _time_regular(cluster: list[_TaskTrace]) -> tuple[bool, str | None]:
    times = [item.at for item in cluster if item.at is not None]
    if len(times) < SUGGEST_SUPPORT:
        return False, None
    hour_minute = Counter((t.hour, t.minute) for t in times)
    (hour, minute), count = hour_minute.most_common(1)[0]
    if count < SUGGEST_SUPPORT:
        return False, None
    return True, f"{minute} {hour} * * *"


def _normalize_label(task: str) -> str:
    return " ".join(task.strip().split())


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _datetime_from_trace_filename(name: str) -> str | None:
    prefix = name.split("_", 1)[0]
    try:
        dt = datetime.strptime(prefix, "%Y-%m-%dT%H-%M-%S")
    except ValueError:
        return None
    return dt.isoformat()


__all__ = [
    "JACCARD_THRESHOLD",
    "RecurringPattern",
    "jaccard",
    "list_patterns",
    "load_trace_tasks",
    "match_pattern",
    "mine_patterns",
    "pattern_summary",
    "suggest_pattern_lines",
    "task_tokens",
]
