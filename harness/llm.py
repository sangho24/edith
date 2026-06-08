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


def _max_output_tokens() -> int:
    """응답 최대 토큰. EDITH_MAX_TOKENS로 조정(기본 2048).

    낮추면 비용↓·속도↑ + 무료 티어 TPM(입력+max_output 합산 과금)에 들어가기 쉬움.
    에이전트 루프의 중간(tool 호출)·최종 답변 모두 2048이면 충분.
    """
    try:
        return int(os.environ.get("EDITH_MAX_TOKENS", "2048"))
    except ValueError:
        return 2048


def _model_env(provider_key: str, default: str) -> str:
    """Common GUI model override first, provider-specific env second."""
    return os.environ.get("EDITH_MODEL") or os.environ.get(provider_key, default)


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
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise RuntimeError("pip install anthropic") from e

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수 없음. .env 파일 또는 export 필요.")
        self.model = model or _model_env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
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
            max_tokens=_max_output_tokens(),
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
        self.model = model or _model_env("XAI_MODEL_FAST", "grok-4-fast")
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
            "max_tokens": _max_output_tokens(),
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        return _openai_response_to_anthropic(resp)


class GeminiLLM:
    """Google Gemini API 래퍼. OpenAI SDK 호환 엔드포인트 사용.

    무료 tier 가 넉넉 (1,500 req/day · 1M tokens/day).
    Anthropic-style messages/tools 입력 → OpenAI 형식 변환 → 호출 → 다시 변환.

    GrokLLM 과 거의 동일하지만 base_url, env var, model 만 다름.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        max_retries: int = 5,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("pip install openai") from e

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY 환경변수 없음. .env 파일 또는 export 필요.")
        self.model = model or _model_env("GEMINI_MODEL_FAST", "gemini-2.5-flash")
        # max_retries 5 — Gemini Free tier 의 5 RPM 한도 자동 처리.
        # OpenAI SDK 가 retry-after 헤더 honor 하면서 exponential backoff.
        self.client = OpenAI(api_key=key, base_url=base_url, max_retries=max_retries)

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
            "max_tokens": _max_output_tokens(),
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        return _openai_response_to_anthropic(resp)


class GroqCloudLLM:
    """Groq Cloud API 래퍼 (xAI Grok 와 다름 — Llama 3.3 70B 등 free tier 호스팅).

    OpenAI SDK 호환. base_url 만 다름.

    Free tier:
    - 30 RPM (Gemini Free 5 RPM 의 6배)
    - 14,400 RPD
    - Llama 3.3 70B Versatile, Llama 3.1 8B Instant 등

    한국어 quality: Gemini 보다 약간 떨어지지만 일상 사용엔 충분.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        max_retries: int = 5,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("pip install openai") from e

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY 환경변수 없음. .env 파일 또는 export 필요.")
        self.model = model or _model_env("GROQ_MODEL_FAST", "llama-3.3-70b-versatile")
        self.client = OpenAI(api_key=key, base_url=base_url, max_retries=max_retries)

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
            "max_tokens": _max_output_tokens(),
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        return _openai_response_to_anthropic(resp)


# ── Factory ─────────────────────────────────────────────────────────────


def get_llm() -> AnthropicLLM | GeminiLLM | GrokLLM | GroqCloudLLM | MockLLM:
    """env 에 따라 적절한 LLM 클라이언트 반환.

    EDITH_LLM:
    - "mock"      → MockLLM
    - "gemini"    → GeminiLLM (Google AI Studio, 5 RPM free)
    - "groq"      → GroqCloudLLM (Groq Cloud, 30 RPM free, Llama 3.3 70B)
    - "grok"      → GrokLLM (xAI)
    - "anthropic" (또는 그 외) → AnthropicLLM (Claude)
    """
    mode = os.environ.get("EDITH_LLM", "anthropic").lower()
    if mode == "mock":
        return MockLLM()
    if mode == "gemini":
        return GeminiLLM()
    if mode == "groq":
        return GroqCloudLLM()
    if mode == "grok":
        return GrokLLM()
    return AnthropicLLM()
