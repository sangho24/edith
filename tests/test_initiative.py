"""Phase 5.2 F26 — 선제적 주도 엔진 v1 테스트.

run_checkin · PushGate · suppression · anti-atrophy 단위 검증.
모든 시각은 now_iso로 주입(결정성). compose_brief 신호는 fixture 파일로 셋업.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from harness.initiative import (
    ATROPHY_PROTECTED,
    PushGate,
    Suggestion,
    SuggestionGenerator,
    is_atrophy_protected,
    record_feedback,
    run_checkin,
)

# 평일(수요일) / 주말(토요일) 고정 시각.
WEEKDAY_ISO = "2026-05-27T08:00:00+00:00"  # 2026-05-27 = Wed
WEEKEND_ISO = "2026-05-30T08:00:00+00:00"  # 2026-05-30 = Sat


@pytest.fixture
def edith_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """compose_brief가 EventKit/실파일 안 타도록 fixture 경로 강제."""
    (tmp_path / "raw" / "calendar").mkdir(parents=True)
    (tmp_path / "raw" / "mail").mkdir(parents=True)
    (tmp_path / "raw" / "digest").mkdir(parents=True)
    (tmp_path / "raw" / "health").mkdir(parents=True)
    (tmp_path / "harness").mkdir(parents=True)
    monkeypatch.setenv(
        "EDITH_CALENDAR_FIXTURE", str(tmp_path / "raw" / "calendar" / "events.json")
    )
    return tmp_path


def _setup_urgent_mail(home: Path, subjects: list[str]) -> None:
    """urgent 메일 fixture — mail.triage가 urgent로 분류하도록 '긴급:' 제목 사용."""
    msgs = [
        {
            "id": f"u{i}",
            "sender": "boss@x.com",
            "subject": subj,
            "snippet": "",
            "received_at": "2026-05-27T07:00:00+00:00",
            "labels": [],
            "unread": True,
        }
        for i, subj in enumerate(subjects)
    ]
    (home / "raw" / "mail" / "messages.json").write_text(
        json.dumps(msgs, ensure_ascii=False), encoding="utf-8"
    )


# ── anti-atrophy ──


def test_is_atrophy_protected_membership() -> None:
    for cat in ATROPHY_PROTECTED:
        assert is_atrophy_protected(cat)
    assert not is_atrophy_protected("urgent_mail")
    assert not is_atrophy_protected("unknown")


def test_atrophy_gate_strips_action_hint() -> None:
    """보호 카테고리는 run_checkin을 거치며 action_hint가 None이 된다."""
    home_marker = "daily_note"
    s = Suggestion(
        id="x",
        category=home_marker,
        scope="personal",
        title="오늘 일기",
        why="저녁 회고 시간",
        signal_key="daily_note::today",
        score=5.0,
        action_hint="대신 써드릴까요",
    )
    # 직접 Gate 헬퍼 검증
    from harness.initiative import _apply_atrophy_gate

    _apply_atrophy_gate([s])
    assert s.action_hint is None


def test_non_protected_keeps_action_hint() -> None:
    s = Suggestion(
        id="x",
        category="urgent_mail",
        scope="personal",
        title="긴급 메일",
        why="미답",
        signal_key="urgent_mail::x",
        score=9.0,
        action_hint="답장 초안 작성",
    )
    from harness.initiative import _apply_atrophy_gate

    _apply_atrophy_gate([s])
    assert s.action_hint == "답장 초안 작성"


# ── PushGate ──


def test_pushgate_weekday_cap() -> None:
    gate = PushGate(weekday_cap=4, weekend_cap=2)
    assert gate.cap_for(date(2026, 5, 27)) == 4  # Wed


def test_pushgate_weekend_cap_more_conservative() -> None:
    gate = PushGate(weekday_cap=4, weekend_cap=2)
    assert gate.cap_for(date(2026, 5, 30)) == 2  # Sat
    assert gate.cap_for(date(2026, 5, 31)) == 2  # Sun


def test_pushgate_remaining_respects_ledger() -> None:
    gate = PushGate(weekday_cap=4)
    assert gate.remaining({"2026-05-27": 4}, WEEKDAY_ISO) == 0
    assert gate.remaining({"2026-05-27": 1}, WEEKDAY_ISO) == 3
    assert gate.remaining({}, WEEKDAY_ISO) == 4


def test_pushgate_filter_takes_top_score_within_room() -> None:
    gate = PushGate(weekday_cap=2)
    cands = [
        Suggestion("a", "urgent_mail", "personal", "A", "", "k_a", score=3.0),
        Suggestion("b", "urgent_mail", "personal", "B", "", "k_b", score=9.0),
        Suggestion("c", "urgent_mail", "personal", "C", "", "k_c", score=6.0),
    ]
    out = gate.filter(cands, {}, WEEKDAY_ISO)
    assert [s.id for s in out] == ["b", "c"]  # top-2 by score


def test_pushgate_filter_empty_when_no_room() -> None:
    gate = PushGate(weekday_cap=4)
    cands = [Suggestion("a", "urgent_mail", "personal", "A", "", "k_a", score=9.0)]
    assert gate.filter(cands, {"2026-05-27": 4}, WEEKDAY_ISO) == []


# ── SuggestionGenerator ──


def test_generator_urgent_mail_only(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: 계약서 검토", "긴급: 서버 다운"])
    cands = SuggestionGenerator().generate(edith_home, "morning", WEEKDAY_ISO)
    assert len(cands) == 2
    assert all(c.category == "urgent_mail" for c in cands)
    assert all(c.action_hint == "답장 초안 작성" for c in cands)


def test_generator_empty_when_no_signals(edith_home: Path) -> None:
    cands = SuggestionGenerator().generate(edith_home, "morning", WEEKDAY_ISO)
    assert cands == []


# ── run_checkin ──


def test_run_checkin_empty_pushes_nothing(edith_home: Path) -> None:
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    assert out["slot"] == "morning"
    assert out["candidates_n"] == 0
    assert out["pushed"] == []
    assert out["suppressed_n"] == 0


def test_run_checkin_pushes_urgent_mail(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: 계약서 검토"])
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    assert out["candidates_n"] == 1
    assert len(out["pushed"]) == 1
    pushed = out["pushed"][0]
    assert pushed["category"] == "urgent_mail"
    assert pushed["status"] == "shown"
    # push_ledger 증가 확인
    ledger = json.loads(
        (edith_home / "harness" / "suggestions.json").read_text(encoding="utf-8")
    )["push_ledger"]
    assert ledger["2026-05-27"] == 1


def test_run_checkin_respects_cap_when_ledger_full(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: A", "긴급: B"])
    # 미리 ledger를 cap까지 채움
    (edith_home / "harness" / "suggestions.json").write_text(
        json.dumps({"push_ledger": {"2026-05-27": 4}, "last": []}),
        encoding="utf-8",
    )
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO, weekday_cap=4)
    assert out["candidates_n"] == 2
    assert out["pushed"] == []  # cap 도달 → 푸시 0


def test_run_checkin_weekend_cap_more_conservative(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: A", "긴급: B", "긴급: C"])
    out = run_checkin(
        edith_home, "morning", now_iso=WEEKEND_ISO, weekday_cap=4, weekend_cap=2
    )
    assert out["candidates_n"] == 3
    assert len(out["pushed"]) == 2  # 주말 cap=2


def test_run_checkin_suppresses_recent_rejected(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: 계약서 검토"])
    # 같은 signal_key를 어제 reject — 7일 윈도우 안이므로 억제돼야 함
    record_feedback(
        edith_home,
        "urgent_mail::긴급: 계약서 검토",
        "rejected",
        now_iso="2026-05-26T08:00:00+00:00",
    )
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    assert out["candidates_n"] == 1
    assert out["suppressed_n"] == 1
    assert out["pushed"] == []


def test_run_checkin_old_rejection_not_suppressed(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: 계약서 검토"])
    # 30일 전 reject — 7일 윈도우 밖 → 억제 안 됨
    record_feedback(
        edith_home,
        "urgent_mail::긴급: 계약서 검토",
        "rejected",
        now_iso="2026-04-27T08:00:00+00:00",
    )
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    assert out["suppressed_n"] == 0
    assert len(out["pushed"]) == 1
