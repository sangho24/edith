"""PR 72 launchd morning brief schedule sanity tests."""

from __future__ import annotations

import plistlib
from pathlib import Path


def test_morning_launchd_plist_shape() -> None:
    plist_path = Path("scripts/launchd/com.edith.morningbrief.plist")
    data = plistlib.loads(plist_path.read_bytes())

    assert data["Label"] == "com.edith.morningbrief"
    assert data["ProgramArguments"] == ["__EDITH_HOME__/scripts/morning_push.sh"]
    assert data["StartCalendarInterval"] == {"Hour": 9, "Minute": 0}
    assert data["RunAtLoad"] is False
    assert data["WorkingDirectory"] == "__EDITH_HOME__"
    assert data["StandardOutPath"].endswith("/logs/morning_push.launchd.out.log")
    assert data["StandardErrorPath"].endswith("/logs/morning_push.launchd.err.log")


def test_morning_push_script_uses_multi_channel_brief_push() -> None:
    script = Path("scripts/morning_push.sh").read_text()

    assert '$(dirname "${BASH_SOURCE[0]}")/..' in script
    assert "run harness brief --push email,osnotify" in script
    assert "logs" in script
    assert "morning_push.log" in script
