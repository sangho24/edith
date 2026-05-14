"""Phase 4 F15 — Apple Health export.xml 파서 + 집계 테스트."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from harness.integrations.apple_health import (
    AppleHealthExportSource,
    HealthSample,
    MockHealthSource,
    daily_summary,
    format_for_brief,
    get_health_source,
)

KST = timezone(timedelta(hours=9))


def _record(
    rec_type: str,
    value: str,
    start: str,
    end: str,
    unit: str = "count",
    source: str = "Mi Fitness",
) -> str:
    return (
        f'<Record type="{rec_type}" sourceName="{source}" unit="{unit}" '
        f'startDate="{start}" endDate="{end}" value="{value}"/>'
    )


def _export(records: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<HealthData>\n" + "\n".join(records) + "\n</HealthData>\n"
    )


def test_export_parses_steps(tmp_path: Path) -> None:
    p = tmp_path / "export.xml"
    p.write_text(
        _export(
            [
                _record(
                    "HKQuantityTypeIdentifierStepCount",
                    "412",
                    "2026-05-13 08:00:00 +0900",
                    "2026-05-13 08:10:00 +0900",
                ),
                _record(
                    "HKQuantityTypeIdentifierStepCount",
                    "1200",
                    "2026-05-13 12:00:00 +0900",
                    "2026-05-13 12:30:00 +0900",
                ),
            ]
        ),
        encoding="utf-8",
    )
    samples = AppleHealthExportSource(p).samples(date(2026, 5, 13), date(2026, 5, 13))
    assert len(samples) == 2
    assert all(s.type == "steps" for s in samples)
    assert samples[0].source == "Mi Fitness"


def test_export_filters_by_date_range(tmp_path: Path) -> None:
    p = tmp_path / "export.xml"
    p.write_text(
        _export(
            [
                _record(
                    "HKQuantityTypeIdentifierStepCount",
                    "100",
                    "2026-05-10 08:00:00 +0900",
                    "2026-05-10 08:10:00 +0900",
                ),
                _record(
                    "HKQuantityTypeIdentifierStepCount",
                    "200",
                    "2026-05-15 08:00:00 +0900",
                    "2026-05-15 08:10:00 +0900",
                ),
            ]
        ),
        encoding="utf-8",
    )
    samples = AppleHealthExportSource(p).samples(date(2026, 5, 12), date(2026, 5, 16))
    assert len(samples) == 1
    assert samples[0].value == 200.0


def test_export_skips_unknown_types(tmp_path: Path) -> None:
    p = tmp_path / "export.xml"
    p.write_text(
        _export(
            [
                _record(
                    "HKQuantityTypeIdentifierBodyMass",
                    "70",
                    "2026-05-13 08:00:00 +0900",
                    "2026-05-13 08:00:00 +0900",
                    unit="kg",
                ),
            ]
        ),
        encoding="utf-8",
    )
    assert AppleHealthExportSource(p).samples(date(2026, 5, 13), date(2026, 5, 13)) == []


def test_export_sleep_value_is_duration_minutes(tmp_path: Path) -> None:
    p = tmp_path / "export.xml"
    p.write_text(
        _export(
            [
                _record(
                    "HKCategoryTypeIdentifierSleepAnalysis",
                    "HKCategoryValueSleepAnalysisAsleepUnspecified",
                    "2026-05-12 23:30:00 +0900",
                    "2026-05-13 07:00:00 +0900",
                    unit="",
                ),
            ]
        ),
        encoding="utf-8",
    )
    samples = AppleHealthExportSource(p).samples(date(2026, 5, 12), date(2026, 5, 12))
    assert len(samples) == 1
    assert samples[0].type == "sleep"
    assert samples[0].value == 450.0  # 7시간 30분
    assert samples[0].unit == "min"


def test_export_missing_file_returns_empty(tmp_path: Path) -> None:
    assert AppleHealthExportSource(tmp_path / "nope.xml").samples(
        date(2026, 5, 1), date(2026, 5, 30)
    ) == []


def test_daily_summary_aggregates() -> None:
    day = date(2026, 5, 13)
    dt = datetime(2026, 5, 13, 8, 0, tzinfo=KST)
    samples = [
        HealthSample("steps", 400, "count", dt, dt),
        HealthSample("steps", 600, "count", dt, dt),
        HealthSample("heart_rate", 60, "count/min", dt, dt),
        HealthSample("heart_rate", 80, "count/min", dt, dt),
        HealthSample("sleep", 450, "min", dt, dt),
    ]
    summary = daily_summary(samples, day)
    assert summary["steps"] == 1000.0
    assert summary["heart_rate_avg"] == 70.0
    assert summary["sleep"] == 450.0


def test_format_for_brief() -> None:
    assert format_for_brief({}) == "헬스 데이터 없음"
    line = format_for_brief({"steps": 8231, "sleep": 412, "heart_rate_avg": 64})
    assert "걸음 8231" in line
    assert "수면 412분" in line


def test_mock_health_source_filters_by_date() -> None:
    dt1 = datetime(2026, 5, 10, 8, 0, tzinfo=KST)
    dt2 = datetime(2026, 5, 20, 8, 0, tzinfo=KST)
    src = MockHealthSource(
        [
            HealthSample("steps", 100, "count", dt1, dt1),
            HealthSample("steps", 200, "count", dt2, dt2),
        ]
    )
    got = src.samples(date(2026, 5, 15), date(2026, 5, 25))
    assert len(got) == 1
    assert got[0].value == 200.0


def test_get_health_source_uses_env(tmp_path: Path, monkeypatch) -> None:
    custom = tmp_path / "custom_export.xml"
    monkeypatch.setenv("EDITH_HEALTH_EXPORT", str(custom))
    src = get_health_source(tmp_path / "home")
    assert isinstance(src, AppleHealthExportSource)
    assert src.path == custom


def test_get_health_source_default_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDITH_HEALTH_EXPORT", raising=False)
    src = get_health_source(tmp_path)
    assert isinstance(src, AppleHealthExportSource)
    assert src.path == tmp_path / "raw" / "health" / "export.xml"
