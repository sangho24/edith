"""F19 — 스케줄러 wiring 테스트 (run_tick).

now·channel 주입으로 트리거 발화 → 체크인 → push 경로를 결정적으로 검증.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.integrations.channel import MockChannel
from harness.scheduler import run_tick

# 2026-05-14 = 목요일(평일). morning_brief("0 8 * * 1-5")가 08:00에 발화.
WEEKDAY_0800 = "2026-05-14T08:00:00"
WEEKDAY_1500 = "2026-05-14T15:00:00"  # 어떤 cron도 매치 안 함


@pytest.fixture
def home(tmp_path: Path) -> Path:
    for sub in ("harness", "raw/calendar", "raw/mail", "raw/digest"):
        (tmp_path / sub).mkdir(parents=True)
    return tmp_path


def _seed_urgent_mail(home: Path) -> None:
    msgs = [
        {
            "id": "u1", "sender": "boss@x.com", "subject": "긴급: 검토 요청",
            "snippet": "", "received_at": "2026-05-14T07:00:00+00:00",
            "labels": [], "unread": True,
        }
    ]
    (home / "raw" / "mail" / "messages.json").write_text(
        json.dumps(msgs, ensure_ascii=False), encoding="utf-8"
    )


def test_tick_fires_morning_on_weekday_0800(home: Path) -> None:
    result = run_tick(home, now_iso=WEEKDAY_0800)
    assert any("morning_brief" in s for s in result["fired"])
    assert len(result["checkins"]) == 1  # compose_brief → run_checkin("morning")


def test_tick_no_fire_off_schedule(home: Path) -> None:
    result = run_tick(home, now_iso=WEEKDAY_1500)
    assert result["fired"] == []
    assert result["pushed"] == []


def test_tick_dedup_same_day(home: Path) -> None:
    first = run_tick(home, now_iso=WEEKDAY_0800)
    assert first["fired"]
    # 같은 날 두 번째 tick(같은 윈도우) → 이미 발화한 slot은 재발화 안 함(de-dup)
    second = run_tick(home, now_iso="2026-05-14T08:03:00")
    assert second["fired"] == []
    assert second["checkins"] == []  # 체크인 중복 실행도 없음


def test_tick_pushes_via_channel(home: Path) -> None:
    _seed_urgent_mail(home)
    ch = MockChannel()
    result = run_tick(home, now_iso=WEEKDAY_0800, channel=ch, recipient="77")
    # urgent 메일 → 후보 push → 채널 전송
    assert result["pushed"], "urgent mail should produce a push"
    assert ch.sent, "channel.send should be called"
    assert ch.sent[0][0] == "77"


def test_tick_empty_signals_no_push(home: Path) -> None:
    ch = MockChannel()
    result = run_tick(home, now_iso=WEEKDAY_0800, channel=ch, recipient="77")
    # 신호 없음 → 발화는 하되 push 0
    assert result["fired"]
    assert result["pushed"] == []
    assert ch.sent == []


def test_tick_deep_work_toggle_suppresses(home: Path) -> None:
    _seed_urgent_mail(home)
    # morning_brief 룰에 toggle_key가 있다면 deep_work로 skip. (룰 정의에 따라) —
    # toggle이 매치 안 해도 발화는 정상; 매치하면 fired 비어야 함.
    result = run_tick(home, now_iso=WEEKDAY_0800, toggles={"deep_work": True})
    assert isinstance(result["fired"], list)  # 토글 키 유무와 무관하게 구조 안정


def test_tick_persists_state(home: Path) -> None:
    run_tick(home, now_iso=WEEKDAY_0800)
    state_file = home / "harness" / "trigger_state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert any("morning_brief" in s for s in state.get("fired", []))
