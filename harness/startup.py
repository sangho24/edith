"""First-run setup checks with user-friendly messages."""

from __future__ import annotations

import os
from collections.abc import Mapping

_PROVIDER_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "grok": "XAI_API_KEY",
    "groq": "GROQ_API_KEY",
}


def required_setup_message(env: Mapping[str, str] | None = None) -> str | None:
    """Return a friendly setup message when required LLM config is missing."""
    env_map = os.environ if env is None else env
    llm = env_map.get("EDITH_LLM", "").strip().lower()
    if not llm:
        return (
            "Edith 설정이 아직 끝나지 않았습니다: EDITH_LLM이 없습니다. "
            "`harness doctor`를 실행해 누락된 설정과 고치는 법을 확인하세요."
        )
    if llm == "mock":
        return None
    key = _PROVIDER_KEYS.get(llm)
    if key is None:
        return (
            f"EDITH_LLM={llm} 값이 지원 목록과 맞지 않습니다. "
            "`harness doctor`를 실행해 설정을 점검하세요."
        )
    if not env_map.get(key, "").strip():
        return (
            f"Edith LLM 설정이 불완전합니다: {key}가 없습니다. "
            "`harness doctor`를 실행해 provider 키와 설정을 점검하세요."
        )
    return None
