"""Phase 3 F6 — Memory recall tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.recall import _extract_support_refs, recall, render_recall


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "entities").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    return tmp_path


def test_empty_query(edith_home: Path) -> None:
    assert recall("", edith_home) == []
    assert recall("   ", edith_home) == []


def test_no_match(edith_home: Path) -> None:
    (edith_home / "wiki" / "entities" / "x.md").write_text("# X\n어떤 내용", encoding="utf-8")
    assert recall("존재하지않는키워드", edith_home) == []


def test_wiki_match_with_support_refs(edith_home: Path) -> None:
    (edith_home / "wiki" / "entities" / "김교수.md").write_text(
        """---
type: entity
scope: school
support_refs:
  - raw/meetings/2026-04-25.md
  - raw/captures/2026-04-26.md
confidence: high
last_updated: 2026-04-28
---

# 김교수

ICLR 2026 area chair. transformer interpretability 연구.
""",
        encoding="utf-8",
    )
    hits = recall("ICLR", edith_home)
    assert len(hits) == 1
    assert hits[0].type == "wiki_entity"
    assert hits[0].path == "wiki/entities/김교수.md"
    assert "raw/meetings/2026-04-25.md" in hits[0].support_refs
    assert "raw/captures/2026-04-26.md" in hits[0].support_refs
    assert "ICLR" in hits[0].snippet


def test_raw_match(edith_home: Path) -> None:
    (edith_home / "raw" / "captures" / "memo.md").write_text(
        "오늘 transformer interpretability 논문 읽음",
        encoding="utf-8",
    )
    hits = recall("interpretability", edith_home)
    assert len(hits) == 1
    assert hits[0].type == "raw"
    assert hits[0].path == "raw/captures/memo.md"
    # raw는 자기 자신이 source
    assert hits[0].support_refs == ["raw/captures/memo.md"]


def test_wiki_score_higher_than_raw(edith_home: Path) -> None:
    """wiki 결과가 raw 결과보다 score 높음 — 컴파일된 지식 우선."""
    (edith_home / "wiki" / "concepts" / "x.md").write_text("transformer", encoding="utf-8")
    (edith_home / "raw" / "captures" / "y.md").write_text("transformer", encoding="utf-8")
    hits = recall("transformer", edith_home)
    assert hits[0].type.startswith("wiki_")
    assert hits[0].score > hits[1].score


def test_score_by_count(edith_home: Path) -> None:
    """매치 빈도 많은 페이지가 score 높음."""
    (edith_home / "wiki" / "concepts" / "many.md").write_text("X X X X X 다섯 번", encoding="utf-8")
    (edith_home / "wiki" / "concepts" / "one.md").write_text("X 한 번 있음", encoding="utf-8")
    hits = recall("X", edith_home)
    assert hits[0].path == "wiki/concepts/many.md"


def test_top_k_limit(edith_home: Path) -> None:
    for i in range(15):
        (edith_home / "wiki" / "concepts" / f"c{i}.md").write_text(f"target {i}", encoding="utf-8")
    hits = recall("target", edith_home, top_k=5)
    assert len(hits) == 5


def test_extract_support_refs() -> None:
    text = """---
type: entity
support_refs:
  - raw/a.md
  - raw/b.md
confidence: medium
---

content
"""
    refs = _extract_support_refs(text)
    assert refs == ["raw/a.md", "raw/b.md"]


def test_extract_support_refs_no_frontmatter() -> None:
    assert _extract_support_refs("# No fm\nbody") == []


def test_extract_support_refs_empty_list() -> None:
    text = "---\ntype: entity\nsupport_refs:\nconfidence: high\n---\n\nx"
    # support_refs: 다음에 - 가 없으면 빈 list
    assert _extract_support_refs(text) == []


def test_30_query_support_refs_coverage(edith_home: Path) -> None:
    """F6 머지 기준 — 30개 query 중 wiki hit이 있는 것은 support_refs 100% 첨부."""
    # seed wiki
    (edith_home / "wiki" / "entities" / "seed.md").write_text(
        """---
type: entity
scope: personal
support_refs:
  - raw/captures/seed.md
confidence: high
last_updated: 2026-04-28
---

# Seed

queries: alpha beta gamma delta epsilon zeta eta theta iota kappa
lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega
plus extra1 extra2 extra3 extra4 extra5 extra6
""",
        encoding="utf-8",
    )
    queries = [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "zeta",
        "eta",
        "theta",
        "iota",
        "kappa",
        "lambda",
        "mu",
        "nu",
        "xi",
        "omicron",
        "pi",
        "rho",
        "sigma",
        "tau",
        "upsilon",
        "phi",
        "chi",
        "psi",
        "omega",
        "extra1",
        "extra2",
        "extra3",
        "extra4",
        "extra5",
        "extra6",
    ]
    assert len(queries) == 30
    coverage = 0
    for q in queries:
        hits = recall(q, edith_home)
        wiki_hits = [h for h in hits if h.type.startswith("wiki_")]
        if wiki_hits:
            assert wiki_hits[0].support_refs, f"q={q}: support_refs empty"
            coverage += 1
    assert coverage == 30  # 100% 첨부


def test_render_recall_empty() -> None:
    text = render_recall([], "x")
    assert "기억이 없습니다" in text


def test_render_recall_with_hits(edith_home: Path) -> None:
    (edith_home / "wiki" / "entities" / "x.md").write_text(
        "---\ntype: entity\nsupport_refs:\n  - raw/a.md\nconfidence: medium\n---\n\nfoo bar",
        encoding="utf-8",
    )
    hits = recall("foo", edith_home)
    text = render_recall(hits, "foo")
    assert "foo" in text
    assert "1개 hit" in text
    assert "raw/a.md" in text
