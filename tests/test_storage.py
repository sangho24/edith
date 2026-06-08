"""T1.3 — atomic JSON storage helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import storage


def test_atomic_write_json_replace_failure_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"ok": "old"}), encoding="utf-8")

    def fail_replace(src: Path, dst: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        storage.atomic_write_json(path, {"ok": "new"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": "old"}
