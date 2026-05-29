"""F18 — MCP runtime bridge (spike).

목표: Edith의 standalone Python runtime(uvicorn/CLI로 도는 본체)이 MCP 서버의
tool(`mcp__*`)을 호출하게 한다.

**핵심 미해결(spike의 본질)**: standalone runtime엔 MCP client가 없다. PlayMCP 같은
호스팅 MCP는 claude.ai 세션 안에서만 노출된다. Edith 본체가 MCP를 쓰려면 자체 MCP
client(stdio/SSE 연결)가 필요하다. 이 모듈은 그 전까지의 **호출 추상화**를 제공한다:

- `McpToolSpec` — MCP tool 하나를 Edith tool로 노출하기 위한 선언.
- `make_mcp_tool(spec, mcp_call_fn)` — spec을 Edith `Tool`로 래핑. 반환된 tool은
  일반 tool과 똑같이 runtime의 budget·trace·policy 게이트를 상속한다.
- `mcp_call_fn`은 inject 가능(telegram http_post / vps relay forward_fn 패턴).
  실 MCP client가 생기면 그 호출 함수를 주입하고, 테스트에선 mock을 주입한다.

정책 통합 주의(F23에서 wiring): make_mcp_tool이 만든 동적 tool 이름은
`EXTERNAL_WRITE_TOOLS`·`tool_scopes()` lru_cache에 없어 R2/R3 게이트를 그냥
통과한다. 그래서 v1은 **무인증 read-only(is_external_write=False)만** 허용하고,
external-write MCP tool은 approval 라우팅(F23)이 붙기 전까지 생성 자체를 거부한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from harness.state import Context
from harness.tools import Tool

# (mcp_tool_name, args) -> result. 실 MCP client 또는 테스트 mock.
McpCallFn = Callable[[str, dict[str, Any]], Any]


@dataclass(frozen=True)
class McpToolSpec:
    """MCP tool 하나를 Edith tool로 노출하기 위한 선언."""

    mcp_tool_name: str  # "mcp__claude_ai_PlayMCP__YouTubeData-get_transcripts"
    edith_tool_name: str  # "youtube_transcript"
    description: str
    input_schema: dict[str, Any]
    is_external_write: bool = False
    scope: str = "any"  # personal|school|work|any (F23에서 tool_scopes 동적 등록)
    auth_kind: str = "none"  # none | oauth | managed


def _no_client(mcp_tool_name: str, args: dict[str, Any]) -> Any:
    """기본 mcp_call_fn — MCP client 미연결 시 명확히 실패."""
    raise RuntimeError(
        f"MCP client 미연결 — {mcp_tool_name} 호출 불가. "
        "F18 spike: MCP-connected 환경에서 make_mcp_tool(spec, mcp_call_fn=...)로 "
        "실 client를 주입해야 함."
    )


def make_mcp_tool(spec: McpToolSpec, mcp_call_fn: McpCallFn | None = None) -> Tool:
    """McpToolSpec → Edith Tool. runtime 게이트(budget·trace·policy)를 상속.

    v1은 무인증 read-only만. external-write MCP tool은 approval 라우팅(F23) 전까지
    미지원 — 정책 우회(R2 미적용)를 방지하기 위해 생성 단계에서 거부한다.
    """
    if spec.is_external_write:
        raise NotImplementedError(
            f"{spec.edith_tool_name}: external-write MCP tool은 F23(approval 라우팅) "
            "전까지 미지원 — R2 우회 방지."
        )

    call = mcp_call_fn or _no_client

    def _fn(args: dict[str, Any], ctx: Context) -> Any:
        # ctx는 미사용이지만 Tool fn 시그니처(args, ctx) 준수.
        return call(spec.mcp_tool_name, args)

    return Tool(
        name=spec.edith_tool_name,
        description=spec.description,
        input_schema=spec.input_schema,
        fn=_fn,
    )


__all__ = ["McpCallFn", "McpToolSpec", "make_mcp_tool"]
