"""paper_triage LLM tool — F8 arxiv 메타데이터 fetch."""

from __future__ import annotations

from typing import Any

from harness.integrations.arxiv import fetch_arxiv_metadata, parse_arxiv_id
from harness.state import Context
from harness.tools import Tool


def _paper_triage(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    arxiv_input = args["arxiv"]
    arxiv_id = parse_arxiv_id(arxiv_input)
    if not arxiv_id:
        return {"ok": False, "error": f"could not parse arxiv id from {arxiv_input!r}"}
    try:
        meta = fetch_arxiv_metadata(arxiv_id)
    except Exception as e:
        return {"ok": False, "error": f"fetch error: {type(e).__name__}: {e}"}
    if not meta:
        return {"ok": False, "error": "arxiv API returned no entry"}
    return {
        "ok": True,
        "id": meta["id"],
        "title": meta["title"],
        "abstract": meta["abstract"][:600],
        "authors": meta["authors"],
        "primary_category": meta.get("primary_category", ""),
        "suggested_wiki_path": f"wiki/summaries/arxiv_{meta['id'].replace('.', '_')}.md",
    }


PAPER_TRIAGE = Tool(
    name="paper_triage",
    description=(
        "arxiv URL 또는 ID 받아 title·abstract·authors 메타데이터 fetch + "
        "wiki summary 페이지 path 제안. read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "arxiv": {
                "type": "string",
                "description": "arxiv URL (https://arxiv.org/abs/xxx) 또는 ID (2412.12345)",
            },
        },
        "required": ["arxiv"],
    },
    fn=_paper_triage,
)
