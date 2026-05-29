"""체감 데모 시드 테스트 — 시드 파일이 선제 엔진의 5개 신호를 실제로 만든다."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from harness.initiative import (
    calendar_conflict_suggestions,
    preview_checkin,
    reading_suggestions,
)
from harness.seed_demo import KST, build_calendar, build_reading, seed_demo, seed_files

D = date(2026, 5, 29)


def test_seed_files_cover_all_signals() -> None:
    rels = {f.relpath for f in seed_files(D)}
    assert rels == {
        "raw/mail/messages.json",
        "raw/calendar/events.json",
        "raw/digest/latest.json",
        "raw/health/export.xml",
        "raw/reading/queue.json",
    }


def test_calendar_seed_has_one_conflict() -> None:
    events = json.loads(build_calendar(D))
    out = calendar_conflict_suggestions({"events": events}, "morning", "2026-05-29T08:00:00+09:00")
    assert len(out) == 1  # 로드맵 회의 ↔ 클라이언트 콜


def test_reading_seed_has_two_stale() -> None:
    queue = json.loads(build_reading(D))
    out = reading_suggestions(queue, "morning", "2026-05-29T08:00:00+09:00")
    assert len(out) == 1  # 한 건으로 집계
    assert "2건" in out[0].title  # 25일·21일 방치 두 건


def test_seed_demo_writes_then_skips_then_force(tmp_path: Path) -> None:
    r1 = seed_demo(tmp_path, target_date=D)
    assert len(r1["written"]) == 5 and r1["skipped"] == []

    r2 = seed_demo(tmp_path, target_date=D)
    assert r2["written"] == [] and len(r2["skipped"]) == 5  # 기존 보존

    r3 = seed_demo(tmp_path, target_date=D, force=True)
    assert len(r3["written"]) == 5  # 덮어씀


def test_seed_demo_does_not_clobber_existing(tmp_path: Path) -> None:
    """이미 있는 실데이터를 force 없이 건드리지 않는다(raw 보호)."""
    mail = tmp_path / "raw" / "mail" / "messages.json"
    mail.parent.mkdir(parents=True)
    mail.write_text("[]", encoding="utf-8")
    seed_demo(tmp_path, target_date=D)
    assert mail.read_text(encoding="utf-8") == "[]"  # 보존됨


def test_seed_demo_produces_five_categories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overrides = (
        "EDITH_DS_DIGEST_URL",
        "EDITH_DS_DIGEST_LATEST",
        "EDITH_HEALTH_EXPORT",
        "EDITH_MAIL_FIXTURE",
    )
    for k in overrides:
        monkeypatch.delenv(k, raising=False)
    seed_demo(tmp_path, target_date=D)
    monkeypatch.setenv(
        "EDITH_CALENDAR_FIXTURE", str(tmp_path / "raw" / "calendar" / "events.json")
    )
    now_iso = datetime.combine(D, time(8, 0), tzinfo=KST).isoformat()
    pv = preview_checkin(tmp_path, "morning", now_iso=now_iso)
    cats = {s["category"] for s in pv["ranked"]}
    assert {"urgent_mail", "calendar_conflict", "ds_digest", "health", "reading_stale"} <= cats
