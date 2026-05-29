"""F18 — MCP 통합 패키지.

bridge: MCP 서버 tool을 Edith Tool로 래핑하는 런타임 브리지.
(recommender·credential store는 F29/F35에서 추가.)
"""

from harness.mcp.bridge import McpToolSpec, make_mcp_tool

__all__ = ["McpToolSpec", "make_mcp_tool"]
