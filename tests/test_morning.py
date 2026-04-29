"""Phase 3 F4 — Morning Brief composer tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from harness.morning import _build_top3, compose_brief


@pytest.fixture(autouse=True)
def _force_local_calendar_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """모든 morning 테스트는 fixture 기반 (EventKit 호출 X)."""
    monkeypatch.setenv(
        "EDITH_CALENDAR_FIXTURE", str(tmp_path / "raw" / "calendar" / "events.json")
    )


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "calendar").mkdir(parents=True)
    (tmp_path / "raw" / "mail").mkdir(parents=True)
    (tmp_path / "raw" / "digest").mkdir(parents=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path


def _today_iso(hour: int) -> str:
    today = datetime.now(UTC).date()
    return datetime.combine(today, time(hour), tzinfo=UTC).isoformat()


def _setup_calendar(home: Path, n: int = 2) -> None:
    events = [
        {
            "id": f"e{i}",
            "title": f"회의 {i}",
            "start": _today_iso(9 + i),
            "end": _today_iso(10 + i),
            "attendees": [],
        }
        for i in range(n)
    ]
    (home / "raw" / "calendar" / "events.json").write_text(
        json.dumps(events, ensure_ascii=False), encoding="utf-8"
    )


def _setup_mail(home: Path, n_urgent: int = 1, n_important: int = 1) -> None:
    msgs = []
    now = datetime.now(UTC).isoformat()
    for i in range(n_urgent):
        msgs.append(
            {
                "id": f"u{i}",
                "sender": "boss@x.com",
                "subject": f"긴급: 항목 {i}",
                "snippet": "",
                "received_at": now,
                "labels": [],
                "unread": True,
            }
        )
    for i in range(n_important):
        msgs.append(
            {
                "id": f"i{i}",
                "sender": "pm@x.com",
                "subject": f"회의 초청 {i}",
                "snippet": "",
                "received_at": now,
                "labels": [],
                "unread": True,
            }
        )
    (home / "raw" / "mail" / "messages.json").write_text(
        json.dumps(msgs, ensure_ascii=False), encoding="utf-8"
    )


def _setup_digest(home: Path, n: int = 2) -> None:
    items = [{"title": f"흥미로운 논문 {i}", "source": "arxiv", "score": 9 - i} for i in range(n)]
    (home / "raw" / "digest" / "latest.json").write_text(
        json.dumps({"date": "2026-04-28", "items": items}), encoding="utf-8"
    )


# ── compose_brief ──


def test_compose_empty(edith_home: Path) -> None:
    """fixture 모두 없을 때 brief는 동작하되 모두 0/empty."""
    brief = compose_brief(edith_home)
    assert brief.today["n_events"] == 0
    assert brief.mail_summary["n_unread"] == 0
    assert brief.digest["n"] == 0
    assert brief.top3 == []


def test_compose_full(edith_home: Path) -> None:
    _setup_calendar(edith_home, n=2)
    _setup_mail(edith_home, n_urgent=1, n_important=2)
    _setup_digest(edith_home, n=3)

    brief = compose_brief(edith_home)
    assert brief.today["n_events"] == 2
    assert brief.mail_summary["n_unread"] == 3
    assert brief.mail_summary["by_priority"]["urgent"] == 1
    assert brief.mail_summary["by_priority"]["important"] == 2
    assert brief.digest["n"] == 3


def test_top3_priority_order() -> None:
    today = {
        "n_events": 2,
        "events": [
            {"summary": "10:00-11:00 morning meeting"},
            {"summary": "14:00-15:00 lunch sync"},
        ],
    }
    mail_summary = {
        "n_unread": 5,
        "urgent": ["urgent fact"],
        "important": ["important fact"],
        "by_priority": {},
    }
    digest = {"items": [{"title": "interesting paper"}]}

    top3 = _build_top3(today, mail_summary, digest)
    assert len(top3) == 3
    assert "urgent" in top3[0]
    assert "morning meeting" in top3[1]
    # 3rd slot은 두 번째 일정 (1순위가 mail urgent니까)
    assert "lunch sync" in top3[2]


def test_top3_fills_with_important_when_short() -> None:
    today = {"n_events": 0, "events": []}
    mail_summary = {
        "n_unread": 3,
        "urgent": [],
        "important": ["imp1", "imp2", "imp3"],
        "by_priority": {},
    }
    digest = {"items": []}
    top3 = _build_top3(today, mail_summary, digest)
    assert len(top3) == 3
    for i, t in enumerate(top3):
        assert f"imp{i + 1}" in t


def test_top3_max_3() -> None:
    today = {
        "n_events": 5,
        "events": [{"summary": f"e{i}"} for i in range(5)],
    }
    mail_summary = {
        "n_unread": 5,
        "urgent": [f"u{i}" for i in range(3)],
        "important": [],
        "by_priority": {},
    }
    digest = {"items": [{"title": f"d{i}"} for i in range(5)]}
    top3 = _build_top3(today, mail_summary, digest)
    assert len(top3) == 3


# ── render ──


def test_render_includes_all_sections(edith_home: Path) -> None:
    _setup_calendar(edith_home, n=1)
    _setup_mail(edith_home, n_urgent=1)
    _setup_digest(edith_home, n=1)
    brief = compose_brief(edith_home)
    text = brief.render_text()
    assert "Edith" in text
    assert "Top 3" in text
    assert "📅" in text
    assert "📧" in text
    assert "📰" in text


def test_render_empty_brief(edith_home: Path) -> None:
    brief = compose_brief(edith_home)
    text = brief.render_text()
    assert "일정: 없음" in text
    assert "unread 메일: 없음" in text
    assert "ds-digest" in text
