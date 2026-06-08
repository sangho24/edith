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
    calendar_conflict_suggestions,
    candidate_summary,
    digest_suggestions,
    health_suggestions,
    is_atrophy_protected,
    learn_suppression_preferences,
    preview_checkin,
    reading_suggestions,
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


def test_learn_suppression_preferences_counts_rejects_only() -> None:
    feedback = [
        {
            "signal_key": "urgent_mail::A",
            "category": "urgent_mail",
            "status": "rejected",
            "at": "2026-05-01T08:00:00+00:00",
        },
        {
            "signal_key": "urgent_mail::A",
            "category": "urgent_mail",
            "status": "rejected",
            "at": "2026-05-02T08:00:00+00:00",
        },
        {
            "signal_key": "urgent_mail::B",
            "category": "urgent_mail",
            "status": "accepted",
            "at": "2026-05-03T08:00:00+00:00",
        },
    ]

    learned = learn_suppression_preferences(feedback, base_days=7)

    assert learned["category_counts"] == {"urgent_mail": 2}
    assert learned["signal_counts"] == {"urgent_mail::A": 2}
    assert learned["category_days"]["urgent_mail"] == 14
    assert learned["signal_days"]["urgent_mail::A"] == 14


def test_repeated_category_reject_extends_suppression_strength(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: 새 메일"])
    # 10일 전 reject 2회: 기존 7일 window라면 풀리지만 category 학습 window=14일이라 억제.
    record_feedback(
        edith_home,
        "urgent_mail::예전 A",
        "rejected",
        now_iso="2026-05-17T08:00:00+00:00",
        category="urgent_mail",
    )
    record_feedback(
        edith_home,
        "urgent_mail::예전 B",
        "rejected",
        now_iso="2026-05-18T08:00:00+00:00",
        category="urgent_mail",
    )

    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)

    assert out["candidates_n"] == 1
    assert out["suppressed_n"] == 1
    assert out["pushed"] == []


# ── 다중 신호 generator (순수 함수, 결정적) ──

_NOW = "2026-05-29T08:00:00+09:00"


def _ev(summary: str, h1: int, m1: int, h2: int, m2: int) -> dict:
    return {
        "summary": summary,
        "start": f"2026-05-29T{h1:02d}:{m1:02d}:00+09:00",
        "end": f"2026-05-29T{h2:02d}:{m2:02d}:00+09:00",
    }


def test_calendar_conflict_detects_overlap() -> None:
    today = {"events": [_ev("A", 10, 0, 11, 0), _ev("B", 10, 30, 11, 30), _ev("C", 14, 0, 15, 0)]}
    out = calendar_conflict_suggestions(today, "morning", _NOW)
    assert len(out) == 1
    assert out[0].category == "calendar_conflict"
    assert "A" in out[0].title and "B" in out[0].title
    assert out[0].action_hint  # 조정은 대행 가능


def test_calendar_no_conflict_when_back_to_back() -> None:
    # 11:00에 끝나고 11:00에 시작 → 겹치지 않음(경계 비포함).
    today = {"events": [_ev("A", 10, 0, 11, 0), _ev("B", 11, 0, 12, 0)]}
    assert calendar_conflict_suggestions(today, "morning", _NOW) == []


def test_calendar_conflict_ignores_malformed() -> None:
    today = {"events": [{"summary": "no-times"}, _ev("A", 10, 0, 11, 0)]}
    assert calendar_conflict_suggestions(today, "morning", _NOW) == []


def test_digest_suggestion_when_new() -> None:
    digest = {"date": "2026-05-29", "n": 2, "items": [{"title": "X"}]}
    out = digest_suggestions(digest, "morning", _NOW)
    assert len(out) == 1 and out[0].category == "ds_digest"
    assert "2건" in out[0].title


def test_digest_none_when_empty() -> None:
    assert digest_suggestions({"n": 0, "items": []}, "morning", _NOW) == []


def test_health_nudge_when_short_sleep() -> None:
    out = health_suggestions({"sleep": 300.0}, "morning", _NOW)
    assert len(out) == 1
    assert out[0].category == "health"
    assert out[0].action_hint is None  # 건강은 nudge만, 대행 금지


def test_health_none_when_enough_or_missing() -> None:
    assert health_suggestions({"sleep": 420.0}, "morning", _NOW) == []
    assert health_suggestions({}, "morning", _NOW) == []


def test_reading_stale_flags_old_unread_only() -> None:
    queue = [
        {"title": "old", "added_at": "2026-05-04", "read": False},  # 25d → stale
        {"title": "fresh", "added_at": "2026-05-26", "read": False},  # 3d → no
        {"title": "done", "added_at": "2026-04-01", "read": True},  # read → ignore
    ]
    out = reading_suggestions(queue, "morning", _NOW)
    assert len(out) == 1
    assert out[0].category == "reading_stale"
    assert "1건" in out[0].title


def test_candidate_summary_multi_signal() -> None:
    signals = {
        "mail_summary": {"urgent": ["긴급: A"]},
        "today": {"events": [_ev("A", 10, 0, 11, 0), _ev("B", 10, 30, 11, 30)]},
        "digest": {"date": "2026-05-29", "n": 2, "items": [{"title": "X"}]},
        "health": {"sleep": 300.0},
        "reading": [{"title": "old", "added_at": "2026-05-04", "read": False}],
    }
    summary = candidate_summary(signals, "morning", _NOW)
    assert summary["n"] == 5
    assert summary["categories"] == [
        "calendar_conflict",
        "ds_digest",
        "health",
        "reading_stale",
        "urgent_mail",
    ]


# ── generate / preview 통합 ──


def test_generate_includes_digest_and_reading(edith_home: Path) -> None:
    (edith_home / "raw" / "digest" / "latest.json").write_text(
        json.dumps({"date": "2026-05-27", "items": [{"title": "X"}, {"title": "Y"}]}),
        encoding="utf-8",
    )
    (edith_home / "raw" / "reading").mkdir(parents=True, exist_ok=True)
    (edith_home / "raw" / "reading" / "queue.json").write_text(
        json.dumps([{"title": "old", "added_at": "2026-05-01", "read": False}]),
        encoding="utf-8",
    )
    cands = SuggestionGenerator().generate(edith_home, "morning", WEEKDAY_ISO)
    cats = {c.category for c in cands}
    assert "ds_digest" in cats
    assert "reading_stale" in cats


def test_run_checkin_surfaces_calendar_conflict(edith_home: Path) -> None:
    # now_iso(2026-05-27 UTC) 창 안에 들어오도록 그 날짜로 일정 시드.
    day = WEEKDAY_ISO[:10]
    events = [
        {
            "id": "a", "title": "A", "attendees": [],
            "start": f"{day}T10:00:00+09:00", "end": f"{day}T11:00:00+09:00",
        },
        {
            "id": "b", "title": "B", "attendees": [],
            "start": f"{day}T10:30:00+09:00", "end": f"{day}T11:30:00+09:00",
        },
    ]
    (edith_home / "raw" / "calendar" / "events.json").write_text(
        json.dumps(events, ensure_ascii=False), encoding="utf-8"
    )
    out = run_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    cats = {p["category"] for p in out["pushed"]}
    assert "calendar_conflict" in cats


def test_run_checkin_surfaces_recurring_pattern(edith_home: Path) -> None:
    traces_dir = edith_home / "harness" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (traces_dir / f"2026-06-0{i + 1}T09-00-00_{i}.jsonl").write_text(
            json.dumps(
                {
                    "t": 0.0,
                    "kind": "start",
                    "task": "daily standup notes",
                    "scope": "personal",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    out = run_checkin(
        edith_home,
        "morning",
        "2026-06-04T08:00:00+09:00",
        weekday_cap=5,
    )

    pushed = out["pushed"]
    assert pushed[0]["category"] == "recurring_pattern"
    assert pushed[0]["title"] == "🔁 늘 하시던 daily standup notes"
    assert pushed[0]["action_hint"] is None


def test_preview_checkin_does_not_mutate_state(edith_home: Path) -> None:
    _setup_urgent_mail(edith_home, ["긴급: A"])
    pv1 = preview_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    pv2 = preview_checkin(edith_home, "morning", now_iso=WEEKDAY_ISO)
    assert pv1["candidates_n"] == pv2["candidates_n"] == 1
    assert pv1["would_push"] == pv2["would_push"]  # 반복해도 동일(ledger 미소모)
    # 미저장 — suggestions.json 생성 안 됨
    assert not (edith_home / "harness" / "suggestions.json").exists()
