"""memory_recall LLM tool — F6 wiki + raw 검색."""

from __future__ import annotations

from typing import Any

from harness.recall import recall
from harness.state import Context
from harness.tools import Tool


def _memory_recall(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    query = args["query"]
    top_k = int(args.get("top_k", 10))
    hits = recall(query, ctx.edith_home, top_k=top_k)
    return {
        "query": query,
        "n": len(hits),
        "hits": [
            {
                "path": h.path,
                "type": h.type,
                "snippet": h.snippet,
                "support_refs": h.support_refs,
                "score": round(h.score, 2),
            }
            for h in hits
        ],
    }


MEMORY_RECALL = Tool(
    name="memory_recall",
    description=(
        "wiki/ 와 raw/ 안에서 query 검색. 모든 hit에 support_refs (raw 출처) 포함. "
        "사용자 질문에 답할 때 인용 source 확보용."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    fn=_memory_recall,
)
