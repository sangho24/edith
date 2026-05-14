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


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    """frontmatter YAML 블록을 dict로 파싱. 없거나 깨졌으면 None."""
    if not _has_frontmatter(content):
        return None
    stripped = content.lstrip()
    end = stripped.find("\n---", 4)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(stripped[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _scope_conflict(page_scope: Any, task_scope: str) -> bool:
    """R3 — page의 concrete scope가 task scope와 다르면 conflict.

    mixed task는 "분리 후 각각 처리"라 막지 않음. frontmatter scope 없는
    페이지(log.md 등)나 비-concrete 값은 conflict 아님.
    """
    if page_scope not in ("personal", "school", "work"):
        return False
    if task_scope == "mixed":
        return False
    return page_scope != task_scope


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
    content = path.read_text(encoding="utf-8")

    # R3 (A2) — page frontmatter scope vs task scope cross-ref 차단.
    fm = _parse_frontmatter(content)
    page_scope = fm.get("scope") if fm else None
    if _scope_conflict(page_scope, ctx.scope):
        return {
            "exists": True,
            "content": None,
            "blocked": True,
            "reason": (
                f"R3: page scope={page_scope}, task scope={ctx.scope} — "
                f"cross-scope read 차단"
            ),
        }
    return {"exists": True, "content": content}


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
        # R3 (A2) — cross-scope 페이지는 검색 결과에서 제외 (snippet leak 방지).
        fm = _parse_frontmatter(text)
        if fm and _scope_conflict(fm.get("scope"), ctx.scope):
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
