"""Phase 4 F15 — Apple Health 연동.

데이터 흐름: 샤오미 Mi Band → Mi Fitness/Zepp 앱 → Apple Health 동기화.
즉 Apple Health가 집계 지점이다. Python CLI는 HealthKit을 직접 못 건드리므로
Health 앱의 "건강 데이터 내보내기"가 만드는 export.xml을 파싱한다.

scope=personal 고정 — Edith가 다루는 가장 민감한 데이터. cross-scope retrieve 금지.

소스:
- AppleHealthExportSource: export.xml (iterparse — 파일이 수백 MB일 수 있음)
- MockHealthSource: 테스트용
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

# Apple Health record type identifier → Edith 내부 짧은 이름.
# 여기 없는 type은 무시 (Edith가 다루는 지표만 화이트리스트).
_TYPE_ALIASES: dict[str, str] = {
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
}

_DT_FORMAT = "%Y-%m-%d %H:%M:%S %z"


@dataclass(frozen=True)
class HealthSample:
    """건강 지표 한 건의 platform-agnostic 표현."""

    type: str  # "steps" | "heart_rate" | "sleep" | "active_energy" | "distance"
    value: float
    unit: str
    start: datetime
    end: datetime
    source: str = ""  # "Mi Fitness" 등 기록 앱

    @property
    def day(self) -> date:
        return self.start.date()


class HealthSource(Protocol):
    """건강 데이터 source interface.

    구현체: AppleHealthExportSource (실 환경), MockHealthSource (테스트).
    """

    def samples(self, start_date: date, end_date: date) -> list[HealthSample]: ...


class MockHealthSource:
    """테스트용 — 미리 정한 sample 리스트에서 날짜 필터만."""

    def __init__(self, samples: list[HealthSample] | None = None) -> None:
        self._samples = samples or []

    def samples(self, start_date: date, end_date: date) -> list[HealthSample]:
        return [s for s in self._samples if start_date <= s.day <= end_date]


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _DT_FORMAT)
    except ValueError:
        return None


class AppleHealthExportSource:
    """Health 앱 export.xml 파서.

    export.xml은 수백 MB가 될 수 있어 iterparse로 스트리밍 — Record 하나 읽고
    바로 clear(). _TYPE_ALIASES에 없는 type은 건너뛴다.

    sleep은 value가 enum 문자열("...AsleepUnspecified")이라 float 변환 대신
    end-start 지속 시간(분)을 value로 쓴다.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def samples(self, start_date: date, end_date: date) -> list[HealthSample]:
        if not self.path.exists():
            return []

        out: list[HealthSample] = []
        for _, elem in ET.iterparse(self.path, events=("end",)):
            if elem.tag != "Record":
                continue
            sample = self._convert(elem)
            elem.clear()
            if sample is not None and start_date <= sample.day <= end_date:
                out.append(sample)
        return out

    def _convert(self, elem: ET.Element) -> HealthSample | None:
        rec_type = _TYPE_ALIASES.get(elem.get("type", ""))
        if rec_type is None:
            return None
        start = _parse_dt(elem.get("startDate"))
        end = _parse_dt(elem.get("endDate"))
        if start is None or end is None:
            return None

        if rec_type == "sleep":
            value = (end - start).total_seconds() / 60.0
            unit = "min"
        else:
            try:
                value = float(elem.get("value", ""))
            except ValueError:
                return None
            unit = elem.get("unit", "")

        return HealthSample(
            type=rec_type,
            value=value,
            unit=unit,
            start=start,
            end=end,
            source=elem.get("sourceName", ""),
        )


def get_health_source(edith_home: Path) -> HealthSource:
    """환경에 맞는 health source 반환.

    - EDITH_HEALTH_EXPORT 설정 → 그 경로의 export.xml
    - 그 외 → edith_home/raw/health/export.xml
    """
    env_path = os.environ.get("EDITH_HEALTH_EXPORT")
    path = Path(env_path) if env_path else edith_home / "raw" / "health" / "export.xml"
    return AppleHealthExportSource(path)


def daily_summary(samples: list[HealthSample], day: date) -> dict[str, float]:
    """하루치 sample을 지표별로 집계.

    steps·active_energy·distance·sleep은 합계, heart_rate는 평균.
    """
    of_day = [s for s in samples if s.day == day]
    summary: dict[str, float] = {}

    for metric in ("steps", "active_energy", "distance", "sleep"):
        vals = [s.value for s in of_day if s.type == metric]
        if vals:
            summary[metric] = round(sum(vals), 1)

    hr = [s.value for s in of_day if s.type == "heart_rate"]
    if hr:
        summary["heart_rate_avg"] = round(sum(hr) / len(hr), 1)

    return summary


def format_for_brief(summary: dict[str, float]) -> str:
    """morning brief 용 한 줄. '걸음 8231 · 수면 412분 · 평균심박 64'."""
    if not summary:
        return "헬스 데이터 없음"
    parts: list[str] = []
    if "steps" in summary:
        parts.append(f"걸음 {int(summary['steps'])}")
    if "sleep" in summary:
        parts.append(f"수면 {int(summary['sleep'])}분")
    if "active_energy" in summary:
        parts.append(f"활동에너지 {summary['active_energy']}")
    if "heart_rate_avg" in summary:
        parts.append(f"평균심박 {int(summary['heart_rate_avg'])}")
    return " · ".join(parts)


__all__ = [
    "AppleHealthExportSource",
    "HealthSample",
    "HealthSource",
    "MockHealthSource",
    "daily_summary",
    "format_for_brief",
    "get_health_source",
]
