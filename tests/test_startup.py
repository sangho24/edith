"""First-run startup message tests."""

from __future__ import annotations

from harness.startup import required_setup_message


def test_required_setup_message_unknown_llm_is_friendly() -> None:
    msg = required_setup_message({"EDITH_LLM": "openai"})

    assert msg is not None
    assert "지원 목록과 맞지 않습니다" in msg
    assert "harness doctor" in msg
