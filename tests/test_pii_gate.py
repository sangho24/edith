"""Phase 5.2 F24 — 발신측 PII 게이트(R5) 테스트.

핵심: 모든 `Channel.send`는 전송 직전 단일 PII chokepoint(`policies.guard_outbound`)를
통과해야 한다. 정상 텍스트는 그대로 전송, PII(이메일/전화/키) 포함 텍스트는
RuntimeError로 차단(전송 안 됨). policies.redact_pii의 카운트도 검증.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness import policies
from harness.integrations.channel import MockChannel, TelegramChannel
from harness.integrations.telegram import TelegramClient

# ── policies.guard_outbound (R5 진입점) ────────────────────────────────────


def test_guard_outbound_passes_clean_text() -> None:
    result = policies.guard_outbound("오늘 일정 3건입니다. 회의는 14시.")
    assert result == {"ok": True, "reason": None}


def test_guard_outbound_blocks_email() -> None:
    result = policies.guard_outbound("연락처는 sam9787@naver.com 입니다")
    assert result["ok"] is False
    assert result["reason"] is not None
    assert "email" in result["reason"]


def test_guard_outbound_blocks_phone() -> None:
    result = policies.guard_outbound("제 번호 010-1234-5678 로 주세요")
    assert result["ok"] is False
    assert "kr_mobile" in (result["reason"] or "")


def test_guard_outbound_blocks_api_key() -> None:
    key = "sk-ant-" + "a" * 30
    result = policies.guard_outbound(f"키는 {key}")
    assert result["ok"] is False
    assert "anthropic_key" in (result["reason"] or "")


def test_check_external_payload_backcompat_signature() -> None:
    """기존 tuple 반환 시그니처는 하위호환 유지."""
    ok, reason = policies.check_external_payload("깨끗한 텍스트")
    assert ok is True
    assert reason is None
    ok2, reason2 = policies.check_external_payload("메일 a@b.com")
    assert ok2 is False
    assert reason2 is not None


# ── redact_pii 카운트 ──────────────────────────────────────────────────────


def test_redact_pii_counts_multiple() -> None:
    text = "메일 a@b.com 과 b@c.org, 전화 010-1111-2222"
    redacted, counts = policies.redact_pii(text)
    assert counts["email"] == 2
    assert counts["kr_mobile"] == 1
    assert "[REDACTED:email]" in redacted
    assert "[REDACTED:kr_mobile]" in redacted
    assert "a@b.com" not in redacted


# ── MockChannel.send ───────────────────────────────────────────────────────


def test_mock_send_passes_clean_text() -> None:
    ch = MockChannel()
    ch.send("u1", "정상 메시지입니다")
    assert ch.sent == [("u1", "정상 메시지입니다")]


def test_mock_send_blocks_pii_and_does_not_record() -> None:
    ch = MockChannel()
    with pytest.raises(RuntimeError, match="R5: PII in outbound"):
        ch.send("u1", "비번 메일은 leak@evil.com 입니다")
    # 차단되면 전송 기록도 없어야 한다.
    assert ch.sent == []


def test_mock_send_blocks_phone() -> None:
    ch = MockChannel()
    with pytest.raises(RuntimeError, match="R5"):
        ch.send("u1", "010-9876-5432 로 전화 주세요")
    assert ch.sent == []


# ── TelegramChannel.send ───────────────────────────────────────────────────


def _telegram_channel() -> tuple[TelegramChannel, list[tuple[str, dict[str, Any]]]]:
    posted: list[tuple[str, dict[str, Any]]] = []

    def fake_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
        posted.append((url, body))
        return {"ok": True}

    client = TelegramClient(token="t", http_post=fake_post)
    return TelegramChannel(client), posted


def test_telegram_send_passes_clean_text() -> None:
    ch, posted = _telegram_channel()
    ch.send("123", "일정 알림입니다")
    assert len(posted) == 1
    assert posted[0][1]["text"] == "일정 알림입니다"


def test_telegram_send_blocks_pii_and_does_not_post() -> None:
    ch, posted = _telegram_channel()
    with pytest.raises(RuntimeError, match="R5: PII in outbound"):
        ch.send("123", "주민번호 900101-1234567 노출")
    # 차단되면 실제 HTTP POST가 발생하지 않아야 한다.
    assert posted == []
