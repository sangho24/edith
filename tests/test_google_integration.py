"""Gmail/Google Calendar 실연동 — 라이브러리·네트워크 없이 service/source 주입으로 검증.

실 OAuth는 사용자 머신에서 `harness oauth google`로만. 여기선 파싱·어댑트·backend 선택 로직.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.calendar import (
    GoogleCalendarSource,
    LocalCalendarSource,
    select_source,
)
from harness.integrations.gmail import MailMessage, MockMailSource
from harness.integrations.google_auth import (
    GOOGLE_SCOPES,
    build_google_service,
    has_google_token,
    token_status,
)
from harness.mail import (
    GmailMessageSource,
    LocalMessageSource,
    classify_priority,
    select_mail_source,
)

# ── google_auth ─────────────────────────────────────────────────────────


def test_google_scopes_cover_gmail_and_calendar() -> None:
    assert "https://www.googleapis.com/auth/gmail.readonly" in GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/gmail.send" in GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/calendar.readonly" in GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/calendar.events" in GOOGLE_SCOPES


def test_build_service_returns_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = MagicMock()
    # service 주입 시 라이브러리/토큰 없이 그대로 반환.
    assert build_google_service("calendar", "v3", service=sentinel) is sentinel


def test_token_status_reads_scopes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token = tmp_path / "google_token.json"
    token.write_text(json.dumps({"scopes": GOOGLE_SCOPES, "account": "me@x.com"}), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(token))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", str(tmp_path / "nope.json"))
    st = token_status()
    assert st["token_exists"] is True
    assert st["secrets_exists"] is False
    assert "https://www.googleapis.com/auth/calendar.readonly" in st["scopes"]


def test_google_calendar_create_event_calls_insert() -> None:
    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-1",
        "summary": "리뷰 미팅",
        "start": {"dateTime": "2026-06-09T10:00:00+09:00"},
        "end": {"dateTime": "2026-06-09T10:30:00+09:00"},
        "htmlLink": "https://cal/evt-1",
    }
    src = GoogleCalendarSource(service=service, calendar_id="work")

    event = src.create_event(
        "리뷰 미팅",
        "2026-06-09T10:00:00+09:00",
        "2026-06-09T10:30:00+09:00",
        description="논문 리뷰",
        location="Zoom",
        attendees=["a@example.com"],
        timezone="Asia/Seoul",
    )

    assert event.id == "evt-1"
    insert = service.events.return_value.insert
    insert.assert_called_once()
    kwargs = insert.call_args.kwargs
    assert kwargs["calendarId"] == "work"
    assert kwargs["sendUpdates"] == "none"
    assert kwargs["body"] == {
        "summary": "리뷰 미팅",
        "start": {"dateTime": "2026-06-09T10:00:00+09:00", "timeZone": "Asia/Seoul"},
        "end": {"dateTime": "2026-06-09T10:30:00+09:00", "timeZone": "Asia/Seoul"},
        "description": "논문 리뷰",
        "location": "Zoom",
        "attendees": [{"email": "a@example.com"}],
    }


def test_google_calendar_create_event_missing_token_safe_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing.json"))
    src = GoogleCalendarSource()
    with pytest.raises(RuntimeError, match="Google 토큰 없음"):
        src.create_event("x", "2026-06-09T10:00:00+09:00", "2026-06-09T10:30:00+09:00")


def test_has_google_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token = tmp_path / "t.json"
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(token))
    assert has_google_token() is False
    token.write_text("{}", encoding="utf-8")
    assert has_google_token() is True


# ── GoogleCalendarSource (service 주입) ──────────────────────────────────


def _cal_service(items: list[dict]) -> MagicMock:
    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {"items": items}
    return service


def test_google_calendar_parses_timed_and_allday() -> None:
    items = [
        {
            "id": "a",
            "summary": "제품 회의",
            "start": {"dateTime": "2026-06-05T10:00:00+09:00"},
            "end": {"dateTime": "2026-06-05T11:00:00+09:00"},
            "attendees": [{"email": "pm@x.com"}, {"email": "lead@x.com"}],
            "htmlLink": "https://cal/a",
        },
        {
            "id": "b",
            "summary": "휴가",
            "start": {"date": "2026-06-05"},
            "end": {"date": "2026-06-06"},
        },
        {"id": "c", "summary": "깨짐(시간없음)"},  # start/end 없음 → 제외
    ]
    src = GoogleCalendarSource(service=_cal_service(items))
    start = datetime(2026, 6, 5, tzinfo=UTC)
    end = datetime(2026, 6, 6, tzinfo=UTC)
    events = src.list_events(start, end)
    assert len(events) == 2
    timed = next(e for e in events if e.id == "a")
    assert timed.title == "제품 회의"
    assert timed.attendees == ["pm@x.com", "lead@x.com"]
    assert timed.url == "https://cal/a"
    allday = next(e for e in events if e.id == "b")
    assert allday.start.hour == 0  # Edith 시간대(KST) 자정 — UTC midnight 09:00 밀림 없음
    # 모든 이벤트 tz-aware → 정렬·duration 연산에서 naive/aware 혼재 크래시 없음
    assert all(e.start.tzinfo is not None and e.end.tzinfo is not None for e in events)


def _fake_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = tmp_path / "google_token.json"
    token.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(token))


def test_select_source_backend_google(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_token(tmp_path, monkeypatch)  # 토큰 있어야 google backend 선택
    monkeypatch.setenv("EDITH_CALENDAR_BACKEND", "google")
    src = select_source(edith_home=tmp_path)
    assert isinstance(src, GoogleCalendarSource)  # 생성만(빌드는 lazy) → OAuth 안 탐


def test_select_source_google_no_token_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setenv("EDITH_CALENDAR_BACKEND", "google")
    # 토큰 없으면 brief가 깨지지 않게 local로 폴백
    assert isinstance(select_source(edith_home=tmp_path), LocalCalendarSource)


def test_select_source_backend_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDITH_CALENDAR_BACKEND", "local")
    src = select_source(edith_home=tmp_path)
    assert isinstance(src, LocalCalendarSource)


# ── GmailMessageSource 어댑트 + select_mail_source ───────────────────────


def _mm(subject: str, unread: bool = True) -> MailMessage:
    return MailMessage(
        id="1",
        thread_id="t1",
        sender="보스 <boss@x.com>",
        subject=subject,
        snippet="본문",
        date=datetime(2026, 6, 5, 7, 0),
        labels=("INBOX", "UNREAD") if unread else ("INBOX",),
        is_unread=unread,
    )


def test_gmail_message_source_adapts_to_message() -> None:
    src = GmailMessageSource(source=MockMailSource([_mm("긴급: 검토")]))
    msgs = src.list_unread()
    assert len(msgs) == 1
    m = msgs[0]
    assert m.subject == "긴급: 검토"
    assert m.unread is True
    assert m.received_at == datetime(2026, 6, 5, 7, 0)
    assert m.thread_id == "t1"
    # triage가 그대로 동작 (urgent 분류)
    assert classify_priority(m) == "urgent"


def test_select_mail_source_default_is_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("EDITH_MAIL_FIXTURE", raising=False)
    monkeypatch.delenv("EDITH_MAIL_BACKEND", raising=False)
    src = select_mail_source(tmp_path)
    assert isinstance(src, LocalMessageSource)
    assert src.messages_path == tmp_path / "raw" / "mail" / "messages.json"


def test_select_mail_source_gmail_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fake_token(tmp_path, monkeypatch)  # 토큰 있어야 gmail backend 선택
    monkeypatch.delenv("EDITH_MAIL_FIXTURE", raising=False)
    monkeypatch.setenv("EDITH_MAIL_BACKEND", "gmail")
    src = select_mail_source(tmp_path)
    assert isinstance(src, GmailMessageSource)  # 생성만 — 실제 호출 시에만 OAuth


def test_select_mail_gmail_no_token_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing.json"))
    monkeypatch.delenv("EDITH_MAIL_FIXTURE", raising=False)
    monkeypatch.setenv("EDITH_MAIL_BACKEND", "gmail")
    # 토큰 없으면 local로 폴백 (brief가 RuntimeError로 깨지지 않게)
    assert isinstance(select_mail_source(tmp_path), LocalMessageSource)
