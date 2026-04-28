"""Phase 3 F4 — github_workflow integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.integrations.github_workflow import (
    cron_for_kst_time,
    get_crons,
    parse_cron_to_kst,
    set_cron,
)

SAMPLE_WORKFLOW = """name: Daily DS Digest

on:
  schedule:
    # KST 07:10 = UTC 22:10 (previous day)
    - cron: '10 22 * * *'
  workflow_dispatch: {}

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -m app.jobs.daily_digest
"""


@pytest.fixture
def workflow_file(tmp_path: Path) -> Path:
    p = tmp_path / "daily.yml"
    p.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    return p


# ── get_crons ──


def test_get_crons_single(workflow_file: Path) -> None:
    crons = get_crons(workflow_file)
    assert crons == ["10 22 * * *"]


def test_get_crons_no_schedule(tmp_path: Path) -> None:
    p = tmp_path / "no_sched.yml"
    p.write_text("name: x\non:\n  push:\n    branches: [main]\n", encoding="utf-8")
    assert get_crons(p) == []


def test_get_crons_multiple(tmp_path: Path) -> None:
    p = tmp_path / "multi.yml"
    p.write_text(
        "name: x\non:\n  schedule:\n    - cron: '0 8 * * *'\n    - cron: '0 18 * * *'\n",
        encoding="utf-8",
    )
    assert get_crons(p) == ["0 8 * * *", "0 18 * * *"]


# ── set_cron ──


def test_set_cron_replaces_first(workflow_file: Path) -> None:
    ok, msg = set_cron(workflow_file, "0 23 * * *")
    assert ok
    assert "10 22" in msg
    assert "0 23" in msg
    assert get_crons(workflow_file) == ["0 23 * * *"]


def test_set_cron_preserves_comment(workflow_file: Path) -> None:
    set_cron(workflow_file, "0 23 * * *")
    text = workflow_file.read_text(encoding="utf-8")
    # 위쪽 주석 보존됨
    assert "KST 07:10" in text
    # workflow_dispatch 등 다른 부분도 보존
    assert "workflow_dispatch" in text


def test_set_cron_idx_out_of_range(workflow_file: Path) -> None:
    ok, msg = set_cron(workflow_file, "0 23 * * *", idx=5)
    assert not ok
    assert "not found" in msg


def test_set_cron_no_cron_in_file(tmp_path: Path) -> None:
    p = tmp_path / "x.yml"
    p.write_text("name: x\non:\n  push: {}\n", encoding="utf-8")
    ok, msg = set_cron(p, "0 23 * * *")
    assert not ok
    assert "no cron" in msg


def test_set_cron_missing_file(tmp_path: Path) -> None:
    ok, msg = set_cron(tmp_path / "missing.yml", "0 8 * * *")
    assert not ok


# ── KST <-> UTC ──


def test_cron_for_kst_morning() -> None:
    """KST 08:00 → UTC 23:00 (previous day) → '0 23 * * *'."""
    assert cron_for_kst_time(8, 0) == "0 23 * * *"


def test_cron_for_kst_late_morning() -> None:
    """KST 10:30 → UTC 01:30 → '30 1 * * *'."""
    assert cron_for_kst_time(10, 30) == "30 1 * * *"


def test_cron_for_kst_midnight() -> None:
    """KST 09:00 → UTC 00:00 → '0 0 * * *'."""
    assert cron_for_kst_time(9, 0) == "0 0 * * *"


def test_cron_for_kst_invalid_hour() -> None:
    with pytest.raises(ValueError):
        cron_for_kst_time(25, 0)


def test_parse_cron_to_kst_simple() -> None:
    """'0 23 * * *' → UTC 23:00 → KST 08:00."""
    assert parse_cron_to_kst("0 23 * * *") == (8, 0)


def test_parse_cron_to_kst_other() -> None:
    assert parse_cron_to_kst("30 1 * * *") == (10, 30)


def test_parse_cron_to_kst_complex_returns_none() -> None:
    """월·요일 wildcard 아닌 cron은 None."""
    assert parse_cron_to_kst("0 23 * * 1-5") is None  # 평일만
    assert parse_cron_to_kst("*/15 * * * *") is None  # 매 15분


def test_parse_cron_to_kst_round_trip() -> None:
    """KST 08:00 → cron → KST 08:00."""
    cron = cron_for_kst_time(8, 0)
    assert parse_cron_to_kst(cron) == (8, 0)
