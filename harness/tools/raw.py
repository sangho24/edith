"""raw_* tools — raw/ (immutable) read + capture_text으로 새 파일 추가."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.state import Context
from harness.tools import Tool


def _raw_path(ctx: Context, rel: str) -> Path:
    base = (ctx.edith_home / "raw").resolve()
    full = (ctx.edith_home / rel).resolve()
    if not str(full).startswith(str(base)):
        raise ValueError(f"path escape: {rel}")
    return full


def _raw_read(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    path = _raw_path(ctx, args["path"])
    if not path.exists():
        return {"exists": False, "content": None}
    return {"exists": True, "content": path.read_text(encoding="utf-8")}


def _raw_list(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    rel = args.get("dir", "raw")
    base = _raw_path(ctx, rel)
    if not base.exists() or not base.is_dir():
        return {"files": []}
    files = sorted(
        str(p.relative_to(ctx.edith_home))
        for p in base.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    )
    return {"files": files, "n": len(files)}


def _capture_text(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """raw/captures/에 새 텍스트 저장. raw는 immutable이지만 새 파일 생성은 허용."""
    text = args["text"]
    source = args.get("source", "manual")
    scope = args.get("scope", ctx.scope)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    safe_source = "".join(c if c.isalnum() else "_" for c in source)
    fname = f"{ts}_{safe_source}.md"
    path = ctx.edith_home / "raw" / "captures" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nsource: {source}\nscope: {scope}\ncaptured_at: {ts}\n---\n\n"
    path.write_text(frontmatter + text, encoding="utf-8")
    return {"ok": True, "path": str(path.relative_to(ctx.edith_home))}


RAW_READ = Tool(
    name="raw_read",
    description="raw/ 안 파일 읽기. raw/는 immutable.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    fn=_raw_read,
)

RAW_LIST = Tool(
    name="raw_list",
    description="raw/<dir> 안 파일 목록. dir 생략 시 raw/ 전체.",
    input_schema={
        "type": "object",
        "properties": {"dir": {"type": "string", "default": "raw"}},
    },
    fn=_raw_list,
)

CAPTURE_TEXT = Tool(
    name="capture_text",
    description=(
        "새 텍스트를 raw/captures/에 timestamp 파일로 저장. scope·source frontmatter 자동."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "scope": {
                "type": "string",
                "enum": ["personal", "school", "work"],
            },
            "source": {"type": "string", "default": "manual"},
        },
        "required": ["text"],
    },
    fn=_capture_text,
)
