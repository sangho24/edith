"""wiki_* tools — wiki/ markdown R/W + 키워드 검색.

H7: wiki_write에 frontmatter 자동 삽입 (없으면 prepend, 있으면 보존).
FTS5 기반 검색은 Phase 2에서. 지금은 단순 substring grep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from harness.state import Context
from harness.tools import Tool

# H7: log.md / INDEX.md / contradictions.md 는 frontmatter 강제 안 함
SPECIAL_WIKI_PAGES = {
    "wiki/log.md",
    "wiki/INDEX.md",
    "wiki/contradictions.md",
}


def _wiki_path(ctx: Context, rel: str) -> Path:
    """경로 escape 방지 — wiki/ 안에서만 R/W."""
    base = (ctx.edith_home / "wiki").resolve()
    full = (ctx.edith_home / rel).resolve()
    if not str(full).startswith(str(base)):
        raise ValueError(f"path escape: {rel}")
    return full


def _infer_page_type(rel: str) -> str:
    """경로에서 wiki page type 추론."""
    if "/entities/" in rel:
        return "entity"
    if "/concepts/" in rel:
        return "concept"
    if "/summaries/" in rel:
        return "summary"
    return "unknown"


def _has_frontmatter(content: str) -> bool:
    """content가 '---\\n'으로 시작하는지 (frontmatter 있는지)."""
    return content.lstrip().startswith("---\n")


def _build_frontmatter(args: dict[str, Any], ctx: Context) -> str:
    """H7. args + ctx로 frontmatter dict → YAML 블록 생성."""
    fm = {
        "type": _infer_page_type(args["path"]),
        "scope": args.get("scope", ctx.scope),
        "support_refs": args["support_refs"],
        "confidence": args.get("confidence", "medium"),
        "last_updated": datetime.now(UTC).strftime("%Y-%m-%d"),
    }
    body = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    return f"---\n{body}---\n\n"


def _wiki_read(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    path = _wiki_path(ctx, args["path"])
    if not path.exists():
        return {"exists": False, "content": None}
    return {"exists": True, "content": path.read_text(encoding="utf-8")}


def _wiki_write(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    support_refs = args.get("support_refs", [])
    if not support_refs:
        return {"ok": False, "reason": "support_refs required"}

    rel = args["path"]
    content = args["content"]
    frontmatter_added = False

    # H7: 특수 페이지가 아니고 frontmatter가 없으면 자동 prepend
    if rel not in SPECIAL_WIKI_PAGES and not _has_frontmatter(content):
        content = _build_frontmatter(args, ctx) + content
        frontmatter_added = True

    path = _wiki_path(ctx, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path.relative_to(ctx.edith_home)),
        "frontmatter_auto_added": frontmatter_added,
    }


def _wiki_search(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """초간단 substring grep. FTS5는 H6에서."""
    query = args["query"].lower()
    base = ctx.edith_home / "wiki"
    hits = []
    for md in base.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        if query in text.lower():
            idx = text.lower().find(query)
            start = max(0, idx - 40)
            end = min(len(text), idx + 80)
            hits.append(
                {
                    "path": str(md.relative_to(ctx.edith_home)),
                    "snippet": text[start:end].replace("\n", " "),
                }
            )
            if len(hits) >= 10:
                break
    return {"hits": hits, "n": len(hits)}


WIKI_READ = Tool(
    name="wiki_read",
    description="wiki/ 안 markdown 페이지를 읽는다. path는 'wiki/...' relative.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    fn=_wiki_read,
)

WIKI_WRITE = Tool(
    name="wiki_write",
    description=(
        "wiki/ 안 markdown 페이지를 쓴다 (덮어쓰기). "
        "support_refs (raw 경로 list) 필수 — 비어있으면 거부."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "support_refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "raw/ 경로 list. 모든 fact는 raw에 근거.",
            },
        },
        "required": ["path", "content", "support_refs"],
    },
    fn=_wiki_write,
)

WIKI_SEARCH = Tool(
    name="wiki_search",
    description="wiki/ 안 markdown에서 키워드 검색. 최대 10개 hit.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    fn=_wiki_search,
)
