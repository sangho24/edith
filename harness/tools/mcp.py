"""recommend_mcp tool — F29a MCP 추천기의 LLM 노출 (read-only).

harness.mcp.recommender.recommend()를 Edith Tool로 감싼다. 추천만 — 실제 MCP
호출·연결은 안 함(F18 bridge·F23 정책 선행). PRD docs/08 §4.1 ①.
"""

from __future__ import annotations

from typing import Any

from harness.mcp.recommender import recommend
from harness.state import Context
from harness.tools import Tool


def _recommend_mcp(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    """query에 맞는 MCP 후보를 deterministic 랭킹해 dict로 반환.

    ctx는 미사용이지만 Tool fn 시그니처(args, ctx) 준수.
    """
    query = str(args.get("query", ""))
    top_k = int(args.get("top_k", 3))
    recs = recommend(query, top_k=top_k)
    return {
        "query": query,
        "recommendations": [
            {
                "mcp_id": r.mcp_id,
                "score": r.score,
                "reason_text": r.reason_text,
                "requires_auth": r.requires_auth,
                "scope": r.scope,
                "caution": r.caution,
            }
            for r in recs
        ],
    }


RECOMMEND_MCP = Tool(
    name="recommend_mcp",
    description=(
        "쿼리에 맞는 외부 MCP(youtube/naver/kakao/google/notion) 연결 후보를 "
        "ROI(docs/07) 근거와 함께 추천. read-only — 실제 연결·호출은 안 함."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "추천 기준이 될 사용자 task/질의"},
            "top_k": {"type": "integer", "description": "반환할 추천 개수 (기본 3)"},
        },
        "required": ["query"],
    },
    fn=_recommend_mcp,
)


__all__ = ["RECOMMEND_MCP"]
