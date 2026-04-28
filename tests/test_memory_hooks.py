"""H7 memory hooks — wiki_write의 자동 frontmatter 삽입."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.state import Context, Trace
from harness.tools.wiki import _build_frontmatter, _has_frontmatter, _infer_page_type, _wiki_write


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    (tmp_path / "wiki" / "entities").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "summaries").mkdir(parents=True)
    return Context(
        edith_home=tmp_path,
        scope="personal",
        trace=Trace.start("test"),
    )


def test_infer_entity_type() -> None:
    assert _infer_page_type("wiki/entities/김교수.md") == "entity"


def test_infer_concept_type() -> None:
    assert _infer_page_type("wiki/concepts/transformer.md") == "concept"


def test_infer_summary_type() -> None:
    assert _infer_page_type("wiki/summaries/iclr2026.md") == "summary"


def test_infer_unknown_type() -> None:
    assert _infer_page_type("wiki/INDEX.md") == "unknown"


def test_has_frontmatter_yes() -> None:
    assert _has_frontmatter("---\ntype: entity\n---\n\n# X")
    assert _has_frontmatter("\n   ---\nfoo: bar\n---\n")


def test_has_frontmatter_no() -> None:
    assert not _has_frontmatter("# X\n\nNo frontmatter here")
    assert not _has_frontmatter("--\nnot quite\n")


def test_build_frontmatter_includes_required_fields(ctx: Context) -> None:
    args = {
        "path": "wiki/entities/김교수.md",
        "support_refs": ["raw/meetings/2026-04-25.md"],
    }
    fm = _build_frontmatter(args, ctx)
    assert fm.startswith("---\n")
    assert fm.endswith("---\n\n")
    assert "type: entity" in fm
    assert "scope: personal" in fm
    assert "confidence: medium" in fm
    assert "support_refs:" in fm
    assert "raw/meetings/2026-04-25.md" in fm
    assert "last_updated:" in fm


def test_h7_auto_prepend_frontmatter(ctx: Context) -> None:
    """LLM이 frontmatter 안 적었으면 자동 prepend."""
    args = {
        "path": "wiki/entities/김교수.md",
        "content": "# 김교수\n\nICLR 2026 area chair.",
        "support_refs": ["raw/meetings/2026-04-25.md"],
    }
    result = _wiki_write(args, ctx)
    assert result["ok"]
    assert result["frontmatter_auto_added"]

    written = (ctx.edith_home / "wiki/entities/김교수.md").read_text(encoding="utf-8")
    assert written.startswith("---\n")
    assert "type: entity" in written
    assert "scope: personal" in written
    assert "raw/meetings/2026-04-25.md" in written
    # 원본 content도 유지
    assert "# 김교수" in written
    assert "ICLR 2026 area chair" in written


def test_h7_preserve_existing_frontmatter(ctx: Context) -> None:
    """LLM이 이미 frontmatter 작성했으면 건드리지 않음."""
    custom = (
        "---\n"
        "type: entity\n"
        "scope: school\n"
        "support_refs:\n"
        "  - raw/x.md\n"
        "confidence: high\n"
        "last_updated: 2026-04-01\n"
        "---\n\n"
        "# Custom"
    )
    args = {
        "path": "wiki/entities/y.md",
        "content": custom,
        "support_refs": ["raw/x.md"],
    }
    result = _wiki_write(args, ctx)
    assert not result["frontmatter_auto_added"]

    written = (ctx.edith_home / "wiki/entities/y.md").read_text(encoding="utf-8")
    assert "scope: school" in written  # personal로 덮어쓰지 않음
    assert "confidence: high" in written
    # frontmatter 두 번 안 붙임
    assert written.count("---\n") == 2  # 시작 + 끝


def test_h7_special_pages_no_frontmatter(ctx: Context) -> None:
    """log.md / INDEX.md / contradictions.md 는 frontmatter 안 붙임."""
    args = {
        "path": "wiki/log.md",
        "content": "2026-04-28 14:32 · raw/x.md → entities/y.md",
        "support_refs": ["raw/x.md"],
    }
    result = _wiki_write(args, ctx)
    assert not result["frontmatter_auto_added"]

    written = (ctx.edith_home / "wiki/log.md").read_text(encoding="utf-8")
    assert not written.startswith("---\n")


def test_h7_support_refs_required(ctx: Context) -> None:
    """support_refs 비어있으면 거부 (frontmatter 자동 삽입과 무관)."""
    args = {
        "path": "wiki/entities/x.md",
        "content": "# X",
        "support_refs": [],
    }
    result = _wiki_write(args, ctx)
    assert not result["ok"]
    assert "support_refs" in result["reason"]
