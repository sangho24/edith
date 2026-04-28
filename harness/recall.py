"""Phase 3 F6 — Memory Recall.

`recall(query)` — wiki + raw 안에서 query 검색. 결과는 path + snippet + support_refs.
LLM이 이 결과로 답을 합성하면 모든 fact에 raw source 인용 가능 (R1: 인용 필수).

머지 기준: 30 쿼리 → support_refs 첨부율 100%, hallucination ≤ 2건.
(hallucination 측정은 사용자 정성 평가).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HitType = Literal["wiki_entity", "wiki_concept", "wiki_summary", "wiki_meta", "raw"]


@dataclass
class RecallHit:
    path: str  # repo-relative path
    type: HitType
    snippet: str
    support_refs: list[str] = field(default_factory=list)
    score: float = 0.0


def _hit_type(rel: str) -> HitType:
    if "/entities/" in rel:
        return "wiki_entity"
    if "/concepts/" in rel:
        return "wiki_concept"
    if "/summaries/" in rel:
        return "wiki_summary"
    if rel.startswith("wiki/"):
        return "wiki_meta"
    return "raw"


def _extract_support_refs(text: str) -> list[str]:
    """frontmatter의 support_refs list 추출. 단순 라인 파싱."""
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---\n", 4)
    if end == -1:
        return []
    fm = text[4:end]
    refs: list[str] = []
    in_refs = False
    for line in fm.splitlines():
        if line.startswith("support_refs:"):
            in_refs = True
            continue
        if in_refs:
            if line.startswith("  - "):
                refs.append(line[4:].strip())
            elif line.startswith("- "):
                refs.append(line[2:].strip())
            elif line.strip() and not line.startswith(" "):
                in_refs = False
    return refs


def _make_snippet(text: str, query: str, around: int = 60) -> str:
    idx = text.lower().find(query.lower())
    if idx < 0:
        return text[: around * 2].replace("\n", " ")
    start = max(0, idx - around)
    end = min(len(text), idx + around + len(query))
    return text[start:end].replace("\n", " ").strip()


def recall(query: str, edith_home: Path, top_k: int = 10) -> list[RecallHit]:
    """wiki/ + raw/ markdown에서 query 검색. score는 매치 빈도 기반."""
    if not query.strip():
        return []
    q_lower = query.lower()
    hits: list[RecallHit] = []

    # wiki/ 검색 (1.0 weight)
    wiki_dir = edith_home / "wiki"
    if wiki_dir.exists():
        for md_path in wiki_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8")
            except Exception:
                continue
            count = text.lower().count(q_lower)
            if count == 0:
                continue
            rel = str(md_path.relative_to(edith_home))
            support_refs = _extract_support_refs(text)
            hits.append(
                RecallHit(
                    path=rel,
                    type=_hit_type(rel),
                    snippet=_make_snippet(text, query),
                    support_refs=support_refs or [rel],
                    score=count * 1.0,
                )
            )

    # raw/ 검색 (0.7 weight — wiki에 컴파일된 게 우선)
    raw_dir = edith_home / "raw"
    if raw_dir.exists():
        for md_path in raw_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8")
            except Exception:
                continue
            count = text.lower().count(q_lower)
            if count == 0:
                continue
            rel = str(md_path.relative_to(edith_home))
            hits.append(
                RecallHit(
                    path=rel,
                    type="raw",
                    snippet=_make_snippet(text, query),
                    support_refs=[rel],  # raw는 자기 자신이 source
                    score=count * 0.7,
                )
            )

    hits.sort(key=lambda h: -h.score)
    return hits[:top_k]


def render_recall(hits: list[RecallHit], query: str) -> str:
    if not hits:
        return f"'{query}' 에 대한 기억이 없습니다."
    lines = [f"'{query}' — {len(hits)}개 hit"]
    icons = {
        "wiki_entity": "👤",
        "wiki_concept": "💡",
        "wiki_summary": "📄",
        "wiki_meta": "📁",
        "raw": "📥",
    }
    for h in hits:
        icon = icons.get(h.type, "·")
        lines.append(f"{icon} [{h.type}] {h.path} (score={h.score:.1f})")
        lines.append(f"   {h.snippet[:120]}")
        if h.support_refs and h.type != "raw":
            lines.append(f"   ↳ refs: {', '.join(h.support_refs[:3])}")
    return "\n".join(lines)
