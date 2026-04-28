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
