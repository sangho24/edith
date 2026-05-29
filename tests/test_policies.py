"""H5 policy engine — R1 (raw immutable), R2 (external write), R4 (PII)."""

from __future__ import annotations

from harness import policies


def test_r1_raw_write_blocked() -> None:
    allowed, reason = policies.allow("raw_write", {}, scope="personal")
    assert not allowed
    assert reason is not None
    assert "R1" in reason


def test_r1_raw_delete_blocked() -> None:
    allowed, reason = policies.allow("raw_delete", {"path": "raw/x.md"}, scope="personal")
    assert not allowed
    assert reason is not None and "R1" in reason


def test_r2_gmail_send_blocked() -> None:
    allowed, reason = policies.allow("gmail_send", {"to": "x@y.com"}, scope="personal")
    assert not allowed
    assert reason is not None and "R2" in reason


def test_r2_calendar_create_blocked() -> None:
    allowed, _ = policies.allow("calendar_create", {}, scope="personal")
    assert not allowed


def test_internal_tools_allowed() -> None:
    allowed, reason = policies.allow("wiki_write", {"path": "wiki/x.md"}, scope="personal")
    assert allowed
    assert reason is None


def test_capture_text_allowed() -> None:
    allowed, _ = policies.allow("capture_text", {"text": "hi"}, scope="personal")
    assert allowed


def test_r3_personal_skill_blocked_in_work_task() -> None:
    """health_summary(personal skill)는 work task에서 차단."""
    allowed, reason = policies.allow("health_summary", {}, scope="work")
    assert not allowed
    assert reason is not None and "R3" in reason
    assert "personal" in reason


def test_r3_personal_skill_allowed_in_personal_task() -> None:
    allowed, reason = policies.allow("health_summary", {}, scope="personal")
    assert allowed
    assert reason is None


def test_r3_personal_skill_allowed_in_mixed_task() -> None:
    """mixed task는 분리 후 각각 처리 — R3가 막지 않음."""
    allowed, _ = policies.allow("health_summary", {}, scope="mixed")
    assert allowed


def test_r3_any_scope_skill_never_blocked() -> None:
    """core skill(scope=any) tool은 어느 task scope에서도 허용."""
    for sc in ("personal", "school", "work", "mixed"):
        allowed, _ = policies.allow("wiki_read", {"path": "wiki/x.md"}, scope=sc)  # type: ignore[arg-type]
        assert allowed, f"wiki_read blocked in {sc}"


def test_r3_ds_digest_blocked_in_school_task() -> None:
    """digest_latest(ds-digest skill, personal)는 school task에서 차단."""
    allowed, reason = policies.allow("digest_latest", {}, scope="school")
    assert not allowed
    assert reason is not None and "R3" in reason


# ── F23 — propose_workflow 우회 차단 + 동적 tool 등록 ──────────────────


def test_f23_propose_clean_steps_allowed() -> None:
    args = {"steps": [{"action_type": "calendar_create", "scope": "personal", "params": {}}]}
    allowed, reason = policies.allow("propose_workflow", args, scope="personal")
    assert allowed
    assert reason is None


def test_f23_propose_cross_scope_step_blocked() -> None:
    """personal task 제안에 work scope step → 차단."""
    args = {"steps": [{"action_type": "gmail_send", "scope": "work", "params": {}}]}
    allowed, reason = policies.allow("propose_workflow", args, scope="personal")
    assert not allowed
    assert reason is not None and "F23/R3" in reason


def test_f23_propose_pii_in_params_blocked() -> None:
    """step.params에 PII → 차단 (제안에 PII 영속 방지)."""
    args = {
        "steps": [
            {"action_type": "gmail_send", "scope": "personal",
             "params": {"body": "내 주민번호 900101-1234567"}}
        ]
    }
    allowed, reason = policies.allow("propose_workflow", args, scope="personal")
    assert not allowed
    assert reason is not None and "F23/R4" in reason


def test_f23_propose_mixed_task_allows_any_scope() -> None:
    args = {"steps": [{"action_type": "gmail_send", "scope": "work", "params": {}}]}
    allowed, _ = policies.allow("propose_workflow", args, scope="mixed")
    assert allowed


def test_f23_check_proposal_steps_direct() -> None:
    ok, _ = policies.check_proposal_steps([{"action_type": "x", "params": {"to": "a@b.com"}}],
                                          task_scope="personal")
    assert not ok  # 이메일 PII


def test_f23_register_external_write_tool() -> None:
    name = "test_dynamic_send_f23"
    try:
        allowed, _ = policies.allow(name, {}, scope="personal")
        assert allowed  # 등록 전엔 통과
        policies.register_external_write_tool(name)
        allowed, reason = policies.allow(name, {}, scope="personal")
        assert not allowed and reason is not None and "R2" in reason
    finally:
        policies.EXTERNAL_WRITE_TOOLS.discard(name)


def test_f23_invalidate_tool_scopes_cache() -> None:
    from harness.skills import tool_scopes

    tool_scopes()  # warm
    policies.invalidate_tool_scopes_cache()  # 예외 없이 동작
    assert tool_scopes().get("health_summary") == "personal"


def test_r4_redact_email() -> None:
    text = "Email me at sam9787@naver.com"
    redacted, counts = policies.redact_pii(text)
    assert "sam9787@naver.com" not in redacted
    assert "[REDACTED:email]" in redacted
    assert counts.get("email") == 1


def test_r4_redact_kr_mobile() -> None:
    text = "내 번호는 010-1234-5678 입니다"
    redacted, counts = policies.redact_pii(text)
    assert "010-1234-5678" not in redacted
    assert counts.get("kr_mobile") == 1


def test_r4_redact_anthropic_key() -> None:
    text = "key: sk-ant-api03-XXXXXXXXXXXXXXXXXXXX-abc"
    redacted, counts = policies.redact_pii(text)
    assert "sk-ant-api03" not in redacted
    assert counts.get("anthropic_key") == 1


def test_r4_redact_multiple() -> None:
    text = "전화 010-1111-2222, 메일 a@b.com, 또 다른 c@d.com"
    redacted, counts = policies.redact_pii(text)
    assert counts["kr_mobile"] == 1
    assert counts["email"] == 2
    assert "010-1111-2222" not in redacted


def test_r4_check_external_payload_blocks() -> None:
    allowed, reason = policies.check_external_payload(
        "Hello, my key is sk-ant-api03-XXXXXXXXXXXXXXXXXXXX-abc"
    )
    assert not allowed
    assert reason is not None and "R4" in reason
    assert "anthropic_key" in reason


def test_r4_check_external_payload_clean() -> None:
    allowed, reason = policies.check_external_payload("그냥 평범한 텍스트입니다")
    assert allowed
    assert reason is None


def test_r4_no_false_positive_on_short_strings() -> None:
    """짧은 영문은 PII로 잡지 말 것."""
    text = "I think the answer is yes"
    _, counts = policies.redact_pii(text)
    assert counts == {}
