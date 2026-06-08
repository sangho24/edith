"""CLI command wiring tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from harness.cli import main


class _BriefLike:
    def render_text(self) -> str:
        return "brief body"


def _stub_brief(monkeypatch, tmp_path: Path) -> None:
    import harness.morning as morning

    monkeypatch.setattr(morning, "compose_brief", lambda home, now: _BriefLike())
    monkeypatch.setenv("EDITH_HOME", str(tmp_path))


def test_cli_brief_push_email_uses_email_channel(monkeypatch, tmp_path: Path) -> None:
    _stub_brief(monkeypatch, tmp_path)
    calls: list[tuple[str, str]] = []

    class FakeEmailChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            calls.append((recipient, text))
            return {"ok": True}

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "EmailChannel", FakeEmailChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "email"])

    assert result.exit_code == 0
    assert calls == [("self", "brief body")]
    assert "✓ Email push" in result.output


def test_cli_brief_push_email_reports_safe_failure(monkeypatch, tmp_path: Path) -> None:
    _stub_brief(monkeypatch, tmp_path)

    class FakeEmailChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            raise RuntimeError("EDITH_NOTIFY_EMAIL 없음")

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "EmailChannel", FakeEmailChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "email"])

    assert result.exit_code == 1
    assert "Email push 실패" in result.output
    assert "EDITH_NOTIFY_EMAIL" in result.output


def test_cli_brief_push_multi_channel_continues_after_failure(
    monkeypatch, tmp_path: Path
) -> None:
    _stub_brief(monkeypatch, tmp_path)
    calls: list[tuple[str, str, str]] = []

    class FakeEmailChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            calls.append(("email", recipient, text))
            raise RuntimeError("EDITH_NOTIFY_EMAIL 없음")

    class FakeOsNotifyChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            calls.append(("osnotify", recipient, text))
            return {"ok": True}

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "EmailChannel", FakeEmailChannel)
    monkeypatch.setattr(channel, "OsNotifyChannel", FakeOsNotifyChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "email,osnotify"])

    assert result.exit_code == 0
    assert calls == [
        ("email", "self", "brief body"),
        ("osnotify", "self", "brief body"),
    ]
    assert "Email push 실패" in result.output
    assert "✓ OS notification" in result.output
    assert "--- push summary ---" in result.output
    assert "✗ email:" in result.output
    assert "✓ osnotify:" in result.output


def test_cli_brief_push_all_channels_failed_exits_nonzero(
    monkeypatch, tmp_path: Path
) -> None:
    _stub_brief(monkeypatch, tmp_path)

    class FakeEmailChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            raise RuntimeError("email not configured")

    class FakeOsNotifyChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            return {"ok": False, "unsupported": True, "platform": "linux"}

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "EmailChannel", FakeEmailChannel)
    monkeypatch.setattr(channel, "OsNotifyChannel", FakeOsNotifyChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "email,osnotify"])

    assert result.exit_code == 1
    assert "✗ email:" in result.output
    assert "✗ osnotify:" in result.output


def test_cli_brief_push_osnotify_uses_osnotify_channel(monkeypatch, tmp_path: Path) -> None:
    _stub_brief(monkeypatch, tmp_path)
    calls: list[tuple[str, str]] = []

    class FakeOsNotifyChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            calls.append((recipient, text))
            return {"ok": True}

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "OsNotifyChannel", FakeOsNotifyChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "osnotify"])

    assert result.exit_code == 0
    assert calls == [("self", "brief body")]
    assert "✓ OS notification" in result.output


def test_cli_brief_push_osnotify_reports_unsupported(monkeypatch, tmp_path: Path) -> None:
    _stub_brief(monkeypatch, tmp_path)

    class FakeOsNotifyChannel:
        def send(self, recipient: str, text: str) -> dict[str, Any]:
            return {"ok": False, "unsupported": True, "platform": "linux"}

    import harness.integrations.channel as channel

    monkeypatch.setattr(channel, "OsNotifyChannel", FakeOsNotifyChannel)

    result = CliRunner().invoke(main, ["brief", "--push", "osnotify"])

    assert result.exit_code == 1
    assert "OS notification 실패" in result.output


def test_cli_brief_push_unknown_channel_errors(monkeypatch, tmp_path: Path) -> None:
    _stub_brief(monkeypatch, tmp_path)

    result = CliRunner().invoke(main, ["brief", "--push", "email,nope"])

    assert result.exit_code == 2
    assert "unknown push channel: nope" in result.output
