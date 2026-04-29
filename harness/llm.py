"""LLM client wrappers — Anthropic / xAI Grok / Mock.

EDITH_LLM 환경변수로 분기:
- "mock"     → MockLLM (테스트용)
- "anthropic" (default fallback) → AnthropicLLM (Claude)
- "grok"     → GrokLLM (xAI, OpenAI SDK 호환)

Harness 는 Anthropic-style messages + tools 포맷만 다룸.
GrokLLM 내부에서 양방향 변환.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """LLM 호출 응답. stop_reason은 anthropic SDK 값 형식.

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


# ── GrokLLM (xAI, OpenAI SDK 호환) ──────────────────────────────────────


def _anthropic_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Anthropic tool spec → OpenAI function spec.

    Anthropic: {"name", "description", "input_schema": {...JSONSchema...}}
    OpenAI:    {"type": "function", "function": {"name", "description", "parameters": {...}}}
    """
    if not tools:
        return None
    out = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return out


def _anthropic_messages_to_openai(
    messages: list[dict[str, Any]], system: str
) -> list[dict[str, Any]]:
    """Anthropic messages → OpenAI messages.

    역할 매핑:
    - anthropic user/assistant → openai user/assistant
    - anthropic tool_result block (in user content) → openai 'tool' role message
    - anthropic tool_use block (in assistant content) → openai assistant.tool_calls
    """
    result: list[dict[str, Any]] = []
    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, str):
                result.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # tool_result blocks (after tool_use) — 각각을 'tool' role 로 변환
                text_parts: list[str] = []
                for block in content:
                    btype = block.get("type")
                    if btype == "tool_result":
                        result.append(
                            {
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": str(block.get("content", "")),
                            }
                        )
                    elif btype == "text":
                        text_parts.append(block.get("text", ""))
                # 남은 text 가 있으면 user message 로 (드물지만)
                if text_parts:
                    result.append({"role": "user", "content": "\n".join(text_parts)})

        elif role == "assistant":
            # content 는 anthropic content blocks 의 list
            text_parts = []
            tool_calls = []
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tool_calls.append(
                            {
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(
                                        block.get("input", {}), ensure_ascii=False
                                    ),
                                },
                            }
                        )

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": " ".join(p for p in text_parts if p) or None,
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            result.append(assistant_msg)

    return result


def _openai_response_to_anthropic(resp: Any) -> LLMResponse:
    """OpenAI ChatCompletion → LLMResponse (Anthropic-style content blocks)."""
    choice = resp.choices[0]
    msg = choice.message
    blocks: list[dict[str, Any]] = []

    if msg.content:
        blocks.append({"type": "text", "text": msg.content})

    if getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {"_raw_args": tc.function.arguments}
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                }
            )

    finish = choice.finish_reason
    has_tool = bool(getattr(msg, "tool_calls", None))
    if finish == "tool_calls" or has_tool:
        stop_reason = "tool_use"
    elif finish == "stop":
        stop_reason = "end_turn"
    elif finish == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = finish or "end_turn"

    usage_in = resp.usage.prompt_tokens if resp.usage else 0
    usage_out = resp.usage.completion_tokens if resp.usage else 0

    return LLMResponse(
        stop_reason=stop_reason,
        content_blocks=blocks,
        usage_in=usage_in,
        usage_out=usage_out,
        text=msg.content or "",
    )


class GrokLLM:
    """xAI Grok API 래퍼. OpenAI SDK 호환 (base_url 만 다름).

    Anthropic-style messages/tools 입력을 OpenAI 형식으로 변환하여 호출하고,
    응답을 다시 Anthropic-style content blocks 로 변환해 LLMResponse 로 반환.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.x.ai/v1",
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("pip install openai") from e

        key = api_key or os.environ.get("XAI_API_KEY")
        if not key:
            raise RuntimeError("XAI_API_KEY 환경변수 없음. .env 파일 또는 export 필요.")
        self.model = model or os.environ.get("XAI_MODEL_FAST", "grok-4-fast")
        self.client = OpenAI(api_key=key, base_url=base_url)

    def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> LLMResponse:
        oai_messages = _anthropic_messages_to_openai(messages, system)
        oai_tools = _anthropic_tools_to_openai(tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": 4096,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        return _openai_response_to_anthropic(resp)


# ── Factory ─────────────────────────────────────────────────────────────


def get_llm() -> AnthropicLLM | GrokLLM | MockLLM:
    """env 에 따라 적절한 LLM 클라이언트 반환.

    EDITH_LLM:
    - "mock"      → MockLLM
    - "grok"      → GrokLLM (xAI)
    - "anthropic" (또는 그 외) → AnthropicLLM (Claude)
    """
    mode = os.environ.get("EDITH_LLM", "anthropic").lower()
    if mode == "mock":
        return MockLLM()
    if mode == "grok":
        return GrokLLM()
    return AnthropicLLM()
