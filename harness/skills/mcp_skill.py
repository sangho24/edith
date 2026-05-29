"""mcp skill — F29a MCP 추천기.

recommend_mcp tool을 묶는 manifest. scope=any (추천 자체는 모든 scope에서 안전한
read-only). 실제 MCP 연결·외부 write는 별도 게이트(F23 approval / CLI 토글) 경유.

파일명은 mcp_skill.py — harness/tools/mcp.py(패키지 혼동 방지)와 구분.
"""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import mcp as mcp_tool

SKILL = Skill(
    name="mcp",
    scope="any",
    tools=[mcp_tool.RECOMMEND_MCP],
    eval_globs=["evals/golden/mcp_recommend_youtube.yaml"],
    channels=[],
)
