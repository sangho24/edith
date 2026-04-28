"""LLM client wrapper with mock mode for tests.

EDITH_LLM=mock 환경변수 설정 시 MockLLM 사용.
기본은 AnthropicLLM (Claude Sonnet 4.6).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """LLM 호출 응답. stop_reason은 anthropic SDK 값을 그대로 받음.

    예상 값: "end_turn" | "tool_use" | "max_tokens" | "stop_sequence"
              | "pause_turn" | "refusal" 등. runtime은 "end_turn"·"tool_use"만 분기.
    """

    stop_reason: str
    content_blocks: list[dict[str, Any]] = field(default_factory=list)
    usage_in: int = 0
    usage_out: int = 0
    text: str = ""


class MockLLM:
    """canned 응답을 순서대로 돌려주는 mock. 테스트용."""

    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.responses = responses or []
        self._idx = 0

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> LLMResponse:
        if self._idx >= len(self.responses):
            return LLMResponse(
                stop_reason="end_turn",
                content_blocks=[{"type": "text", "text": "(mock done)"}],
                text="(mock done)",
            )
        r = self.responses[self._idx]
        self._idx += 1
        return r


class AnthropicLLM:
    """Claude API 래퍼. Anthropic SDK 사용."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise RuntimeError("pip install anthropic") from e

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수 없음. .env 파일 또는 export 필요.")
        self.model = model
        self.client = Anthropic(api_key=key)

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> LLMResponse:
        # anthropic SDK는 TypedDict를 요구하지만 dict[str, Any]도 런타임에선 동등.
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=tools,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )
        blocks = [b.model_dump() for b in resp.content]
        text = "".join(b["text"] for b in blocks if b.get("type") == "text")
        return LLMResponse(
            stop_reason=resp.stop_reason or "end_turn",
            content_blocks=blocks,
            usage_in=resp.usage.input_tokens,
            usage_out=resp.usage.output_tokens,
            text=text,
        )


def get_llm() -> AnthropicLLM | MockLLM:
    """env에 따라 mock 또는 anthropic."""
    if os.environ.get("EDITH_LLM") == "mock":
        return MockLLM()
    return AnthropicLLM()
