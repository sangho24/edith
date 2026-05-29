"""Phase 5.2 F26 — 선제적 주도 엔진 v1 (PRD docs/08 §4.2).

Edith가 사용자 질문을 기다리지 않고 먼저 제안(Suggestion)을 푸시하는 엔진.
스케줄러가 정해진 슬롯(morning/midday/evening)에 ``run_checkin``을 부르면:

1. ``morning.compose_brief``의 신호를 읽어 후보 Suggestion을 생성한다(SuggestionGenerator).
2. anti-atrophy Gate — 보호 카테고리(스스로 해야 사용자가 위축되지 않는 것)는
   action_hint를 금지하고 최대 nudge만 남긴다.
3. suppression Gate — 최근 N일 reject 이력이 있는 signal_key는 후보에서 제외한다.
4. PushGate — 그날 이미 푸시한 횟수(push_ledger)가 weekday_cap을 넘으면 거부한다.
   주말엔 cap을 더 보수적으로 줄인다.

run_checkin은 LLM tool이 아니다 — 스케줄러가 직접 부른다. 따라서 skill/tool 등록은 없다.

상태 파일(둘 다 edith_home/harness/ 아래, gitignore 대상, 코드에서 생성):
- ``suggestions.json``        — push_ledger(슬롯별 푸시 카운트) + 마지막 제안 스냅샷
- ``suggestion_feedback.jsonl`` — 사용자 피드백(accept/reject/snooze) append-only 로그

PushGate 로직은 여기에 자체 보유한다. policies.py에 넣지 않는다(R6 마이그레이션은 후속).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from harness.morning import compose_brief

# anti-atrophy 보호 카테고리 — 이 일들은 Edith가 대신 하면 사용자의 역량이 위축된다.
# 보호 카테고리는 action_hint를 받지 못하고(대행 금지), 기껏해야 nudge로만 노출된다.
ATROPHY_PROTECTED: frozenset[str] = frozenset(
    {
        "daily_note",
        "creative_body",
        "new_hypothesis",
        "research_direction",
        "quarterly_rotation",
    }
)

# 슬롯 — 스케줄러가 부르는 시점.
Slot = Literal["morning", "midday", "evening"]

# Suggestion lifecycle 상태.
SuggestionStatus = Literal[
    "proposed", "shown", "accepted", "rejected", "snoozed", "expired"
]

# 기본 파라미터.
DEFAULT_WEEKDAY_CAP = 4
DEFAULT_WEEKEND_CAP = 2
DEFAULT_SUPPRESSION_DAYS = 7

_SUGGESTIONS_FILE = "suggestions.json"
_FEEDBACK_FILE = "suggestion_feedback.jsonl"


@dataclass
class Suggestion:
    """Edith가 사용자에게 먼저 내미는 단일 제안.

    Attributes:
        id: 결정적 식별자(signal_key + slot + day 기반).
        category: 제안 카테고리(urgent_mail / daily_note / ...). 보호셋이면 nudge만.
        scope: personal | school | work | mixed.
        title: 한 줄 제목.
        why: 왜 지금 이 제안을 하는지(신호 근거).
        signal_key: suppression 매칭 키(같은 신호의 반복 제안 억제용).
        score: 우선순위 점수(높을수록 먼저 푸시).
        action_hint: 대행 액션 힌트. 보호 카테고리면 None(대행 금지).
        created_at: 생성 ISO 시각.
        slot: 어느 체크인 슬롯에서 만들어졌는지.
        status: lifecycle 상태.
    """

    id: str
    category: str
    scope: str
    title: str
    why: str
    signal_key: str
    score: float
    action_hint: str | None = None
    created_at: str = ""
    slot: str = "morning"
    status: SuggestionStatus = "proposed"

    def to_dict(self) -> dict:
        """직렬화용 dict."""
        return asdict(self)


def is_atrophy_protected(category: str) -> bool:
    """category가 anti-atrophy 보호셋이면 True (action_hint 금지 대상)."""
    return category in ATROPHY_PROTECTED


# ── 상태 파일 I/O ──


def _harness_dir(edith_home: Path) -> Path:
    """edith_home/harness 디렉토리(없으면 생성)."""
    d = edith_home / "harness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_suggestions_state(edith_home: Path) -> dict:
    """suggestions.json 로드. 없으면 기본 구조 반환.

    구조: {"push_ledger": {"YYYY-MM-DD": int, ...}, "last": [Suggestion dict, ...]}
    """
    path = _harness_dir(edith_home) / _SUGGESTIONS_FILE
    if not path.exists():
        return {"push_ledger": {}, "last": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"push_ledger": {}, "last": []}
    if not isinstance(data, dict):
        return {"push_ledger": {}, "last": []}
    data.setdefault("push_ledger", {})
    data.setdefault("last", [])
    return data


def _save_suggestions_state(edith_home: Path, state: dict) -> None:
    """suggestions.json 저장."""
    path = _harness_dir(edith_home) / _SUGGESTIONS_FILE
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_feedback(edith_home: Path) -> list[dict]:
    """suggestion_feedback.jsonl 의 모든 피드백 레코드 로드(append-only)."""
    path = _harness_dir(edith_home) / _FEEDBACK_FILE
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def record_feedback(
    edith_home: Path,
    signal_key: str,
    status: SuggestionStatus,
    now_iso: str | None = None,
) -> None:
    """사용자 피드백을 suggestion_feedback.jsonl에 append.

    suppression Gate가 reject 레코드를 읽어 같은 신호의 반복 제안을 억제한다.
    """
    rec = {
        "signal_key": signal_key,
        "status": status,
        "at": now_iso or datetime.now(UTC).isoformat(),
    }
    path = _harness_dir(edith_home) / _FEEDBACK_FILE
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 후보 생성 ──


class SuggestionGenerator:
    """compose_brief 신호 → Suggestion 후보.

    v1은 urgent 미답 메일만 후보화한다(mail_summary.urgent 사용).
    카테고리/슬롯이 늘어나면 _generators에 메서드를 추가한다.
    """

    def generate(self, edith_home: Path, slot: str, now_iso: str) -> list[Suggestion]:
        """슬롯에 대한 모든 후보 Suggestion 반환."""
        brief = compose_brief(edith_home)
        out: list[Suggestion] = []
        out += self._from_urgent_mail(brief.mail_summary, slot, now_iso)
        return out

    def _from_urgent_mail(
        self, mail_summary: dict, slot: str, now_iso: str
    ) -> list[Suggestion]:
        """urgent 미답 메일 → urgent_mail 카테고리 후보."""
        out: list[Suggestion] = []
        urgent = mail_summary.get("urgent") or []
        day = now_iso[:10]
        for idx, subject in enumerate(urgent):
            signal_key = f"urgent_mail::{subject}"
            out.append(
                Suggestion(
                    id=f"{day}:{slot}:urgent_mail:{idx}",
                    category="urgent_mail",
                    scope="personal",
                    title=f"긴급 메일 미답: {subject}",
                    why=f"오늘 unread 중 urgent 분류 메일 '{subject}'에 아직 응답 없음",
                    signal_key=signal_key,
                    score=10.0 - idx,
                    action_hint="답장 초안 작성",
                    created_at=now_iso,
                    slot=slot,
                    status="proposed",
                )
            )
        return out


# ── Gate ──


def _apply_atrophy_gate(suggestions: list[Suggestion]) -> list[Suggestion]:
    """anti-atrophy: 보호 카테고리는 action_hint를 제거(대행 금지, nudge만)."""
    for s in suggestions:
        if is_atrophy_protected(s.category):
            s.action_hint = None
    return suggestions


def _recent_rejected_keys(
    feedback: list[dict], now_iso: str, suppression_days: int
) -> set[str]:
    """최근 suppression_days 내 reject 이력이 있는 signal_key 집합."""
    now_d = _parse_date(now_iso)
    rejected: set[str] = set()
    for rec in feedback:
        if rec.get("status") != "rejected":
            continue
        key = rec.get("signal_key")
        at = rec.get("at")
        if not isinstance(key, str) or not isinstance(at, str):
            continue
        rec_d = _parse_date(at)
        if rec_d is None or now_d is None:
            # 날짜 파싱 실패 시 보수적으로 억제(노이즈 방지).
            rejected.add(key)
            continue
        if (now_d - rec_d).days <= suppression_days:
            rejected.add(key)
    return rejected


def _apply_suppression_gate(
    suggestions: list[Suggestion],
    feedback: list[dict],
    now_iso: str,
    suppression_days: int,
) -> tuple[list[Suggestion], int]:
    """최근 reject 된 signal_key 후보 제외. (남은 후보, 억제된 수) 반환."""
    rejected = _recent_rejected_keys(feedback, now_iso, suppression_days)
    kept: list[Suggestion] = []
    suppressed = 0
    for s in suggestions:
        if s.signal_key in rejected:
            suppressed += 1
        else:
            kept.append(s)
    return kept, suppressed


@dataclass
class PushGate:
    """그날 푸시 횟수를 weekday/weekend cap으로 제한.

    push_ledger는 {"YYYY-MM-DD": 이미 푸시한 수}. cap에서 used를 뺀 만큼만 통과.
    주말(토/일)엔 weekend_cap을 적용해 더 보수적으로 민다.
    """

    weekday_cap: int = DEFAULT_WEEKDAY_CAP
    weekend_cap: int = DEFAULT_WEEKEND_CAP

    def cap_for(self, day: date) -> int:
        """해당 날짜의 cap (주말은 weekend_cap)."""
        return self.weekend_cap if day.weekday() >= 5 else self.weekday_cap

    def remaining(self, push_ledger: dict, now_iso: str) -> int:
        """오늘 남은 푸시 가능 수(0 이상)."""
        day = _parse_date(now_iso)
        if day is None:
            return 0
        cap = self.cap_for(day)
        used = int(push_ledger.get(day.isoformat(), 0))
        return max(0, cap - used)

    def filter(
        self, suggestions: list[Suggestion], push_ledger: dict, now_iso: str
    ) -> list[Suggestion]:
        """score 내림차순으로 remaining 개수만 통과시킨다."""
        room = self.remaining(push_ledger, now_iso)
        if room <= 0:
            return []
        ranked = sorted(suggestions, key=lambda s: s.score, reverse=True)
        return ranked[:room]


# ── 날짜 유틸 ──


def _parse_date(iso: str) -> date | None:
    """ISO 문자열에서 date 추출(YYYY-MM-DD 또는 full datetime)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        try:
            return date.fromisoformat(iso[:10])
        except ValueError:
            return None


# ── 진입점 ──


def run_checkin(
    edith_home: Path,
    slot: str,
    now_iso: str | None = None,
    weekday_cap: int = DEFAULT_WEEKDAY_CAP,
    weekend_cap: int = DEFAULT_WEEKEND_CAP,
    suppression_days: int = DEFAULT_SUPPRESSION_DAYS,
) -> dict:
    """체크인 슬롯에서 후보 생성 → Gate → PushGate → 푸시 목록 반환.

    Args:
        edith_home: Edith 홈 디렉토리.
        slot: 체크인 슬롯("morning" | "midday" | "evening").
        now_iso: 현재 시각 ISO(테스트 결정성 위해 주입 가능). 기본 datetime.now(UTC).
        weekday_cap: 평일 일일 푸시 상한.
        weekend_cap: 주말 일일 푸시 상한.
        suppression_days: reject suppression 윈도우(일).

    Returns:
        {"slot", "candidates_n", "pushed": [Suggestion dict, ...], "suppressed_n"}.
        push_ledger를 푸시 수만큼 증가시키고 suggestions.json에 last 스냅샷을 저장한다.
    """
    now_iso = now_iso or datetime.now(UTC).isoformat()

    # 1. 후보 생성
    candidates = SuggestionGenerator().generate(edith_home, slot, now_iso)
    candidates_n = len(candidates)

    # 2. anti-atrophy Gate (보호 카테고리 action_hint 제거)
    candidates = _apply_atrophy_gate(candidates)

    # 3. suppression Gate (최근 reject 된 signal_key 제외)
    feedback = _load_feedback(edith_home)
    candidates, suppressed_n = _apply_suppression_gate(
        candidates, feedback, now_iso, suppression_days
    )

    # 4. PushGate (weekday/weekend cap)
    state = _load_suggestions_state(edith_home)
    push_ledger: dict = state["push_ledger"]
    gate = PushGate(weekday_cap=weekday_cap, weekend_cap=weekend_cap)
    pushed = gate.filter(candidates, push_ledger, now_iso)

    # 5. 상태 갱신 — push_ledger 증가 + last 스냅샷 저장
    for s in pushed:
        s.status = "shown"
    day = _parse_date(now_iso)
    if day is not None and pushed:
        key = day.isoformat()
        push_ledger[key] = int(push_ledger.get(key, 0)) + len(pushed)
    state["push_ledger"] = push_ledger
    state["last"] = [s.to_dict() for s in pushed]
    _save_suggestions_state(edith_home, state)

    return {
        "slot": slot,
        "candidates_n": candidates_n,
        "pushed": [s.to_dict() for s in pushed],
        "suppressed_n": suppressed_n,
    }


__all__ = [
    "ATROPHY_PROTECTED",
    "PushGate",
    "Suggestion",
    "SuggestionGenerator",
    "is_atrophy_protected",
    "record_feedback",
    "run_checkin",
]
