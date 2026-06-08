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
from harness.storage import atomic_write_json, file_lock, read_json_file

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
    data = read_json_file(path, {"push_ledger": {}, "last": []})
    if not isinstance(data, dict):
        return {"push_ledger": {}, "last": []}
    data.setdefault("push_ledger", {})
    data.setdefault("last", [])
    return data


def _save_suggestions_state(edith_home: Path, state: dict) -> None:
    """suggestions.json 저장."""
    path = _harness_dir(edith_home) / _SUGGESTIONS_FILE
    atomic_write_json(path, state)


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
    category: str | None = None,
) -> None:
    """사용자 피드백을 suggestion_feedback.jsonl에 append.

    suppression Gate가 reject 레코드를 읽어 같은 신호의 반복 제안을 억제한다.
    """
    clean_category = category if category else _category_from_signal(signal_key)
    rec = {
        "signal_key": signal_key,
        "status": status,
        "at": now_iso or datetime.now(UTC).isoformat(),
    }
    if clean_category:
        rec["category"] = clean_category
    path = _harness_dir(edith_home) / _FEEDBACK_FILE
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── 후보 생성 ──
#
# 각 신호 카테고리는 순수 함수(signal → list[Suggestion])로 분리한다. compose_brief·
# EventKit·실시간 now에 의존하지 않으므로 candidate_summary 골든에서 결정적으로 검증된다.
# SuggestionGenerator는 compose_brief + 읽기목록으로 signals dict를 만들어 위임만 한다.

# 카테고리별 튜닝 상수.
CALENDAR_CONFLICT_SCORE = 9.0
DIGEST_SCORE = 6.0
HEALTH_SLEEP_MIN_MINUTES = 360.0  # 6h 미만이면 수면 부족 nudge
HEALTH_SCORE = 4.0
READING_STALE_DAYS = 14
READING_SCORE = 3.0


def urgent_mail_suggestions(mail_summary: dict, slot: str, now_iso: str) -> list[Suggestion]:
    """urgent 미답 메일 → urgent_mail 후보."""
    out: list[Suggestion] = []
    urgent = mail_summary.get("urgent") or []
    day = now_iso[:10]
    for idx, subject in enumerate(urgent):
        out.append(
            Suggestion(
                id=f"{day}:{slot}:urgent_mail:{idx}",
                category="urgent_mail",
                scope="personal",
                title=f"긴급 메일 미답: {subject}",
                why=f"오늘 unread 중 urgent 분류 메일 '{subject}'에 아직 응답 없음",
                signal_key=f"urgent_mail::{subject}",
                score=10.0 - idx,
                action_hint="답장 초안 작성",
                created_at=now_iso,
                slot=slot,
                status="proposed",
            )
        )
    return out


def _detect_conflicts(events: list[dict]) -> list[tuple[dict, dict]]:
    """start/end가 시간상 겹치는 이벤트 쌍(시작시각 정렬 기반)."""
    parsed: list[tuple[datetime, datetime, dict]] = []
    for ev in events:
        try:
            s = datetime.fromisoformat(ev["start"])
            e = datetime.fromisoformat(ev["end"])
        except (KeyError, TypeError, ValueError):
            continue
        parsed.append((s, e, ev))
    parsed.sort(key=lambda x: x[0])
    out: list[tuple[dict, dict]] = []
    for i in range(len(parsed)):
        _s1, e1, ev1 = parsed[i]
        for j in range(i + 1, len(parsed)):
            s2, _e2, ev2 = parsed[j]
            if s2 < e1:
                out.append((ev1, ev2))
            else:
                break  # 시작시각 정렬 → 이후 이벤트는 모두 e1 이후 시작
    return out


def _ev_label(ev: dict) -> str:
    return ev.get("summary") or ev.get("title") or "(제목없음)"


def calendar_conflict_suggestions(today: dict, slot: str, now_iso: str) -> list[Suggestion]:
    """오늘 일정 중 시간이 겹치는 쌍 → calendar_conflict 후보."""
    events = today.get("events") or []
    out: list[Suggestion] = []
    day = now_iso[:10]
    for idx, (ev1, ev2) in enumerate(_detect_conflicts(events)):
        t1, t2 = _ev_label(ev1), _ev_label(ev2)
        out.append(
            Suggestion(
                id=f"{day}:{slot}:calendar_conflict:{idx}",
                category="calendar_conflict",
                scope="personal",
                title=f"일정 충돌: {t1} ↔ {t2}",
                why=f"오늘 두 일정 '{t1}'·'{t2}' 시간이 겹침 — 조정 필요",
                signal_key=f"calendar_conflict::{t1}::{t2}",
                score=CALENDAR_CONFLICT_SCORE - idx,
                action_hint="겹치는 일정 조정 제안",
                created_at=now_iso,
                slot=slot,
                status="proposed",
            )
        )
    return out


def digest_suggestions(digest: dict, slot: str, now_iso: str) -> list[Suggestion]:
    """ds-digest 새 항목 → ds_digest 후보(미정리 리마인드)."""
    n = int(digest.get("n", 0) or 0)
    if n <= 0:
        return []
    items = digest.get("items") or []
    first = str(items[0].get("title", "")) if items and isinstance(items[0], dict) else ""
    d_date = digest.get("date") or now_iso[:10]
    why = f"{d_date} digest {n}건 도착 — 아직 정리 안 됨"
    if first:
        why += f" (예: {first[:50]})"
    return [
        Suggestion(
            id=f"{now_iso[:10]}:{slot}:ds_digest:0",
            category="ds_digest",
            scope="personal",
            title=f"ds-digest 새 이슈 {n}건 미정리",
            why=why,
            signal_key=f"ds_digest::{d_date}",
            score=DIGEST_SCORE,
            action_hint="digest 핵심 3개 요약",
            created_at=now_iso,
            slot=slot,
            status="proposed",
        )
    ]


def health_suggestions(health: dict, slot: str, now_iso: str) -> list[Suggestion]:
    """수면 부족(< HEALTH_SLEEP_MIN_MINUTES) → health nudge. 건강은 대행 금지(action_hint 없음)."""
    sleep = health.get("sleep")
    if not isinstance(sleep, int | float) or sleep <= 0 or sleep >= HEALTH_SLEEP_MIN_MINUTES:
        return []
    hours = sleep / 60.0
    return [
        Suggestion(
            id=f"{now_iso[:10]}:{slot}:health:0",
            category="health",
            scope="personal",
            title=f"수면 부족: 어젯밤 {hours:.1f}h",
            why=f"수면 {int(sleep)}분 (<{int(HEALTH_SLEEP_MIN_MINUTES)}분). 컨디션 주의",
            signal_key=f"health_sleep::{now_iso[:10]}",
            score=HEALTH_SCORE,
            action_hint=None,  # nudge only — 건강은 Edith가 대행할 대상 아님
            created_at=now_iso,
            slot=slot,
            status="proposed",
        )
    ]


def reading_suggestions(queue: list[dict], slot: str, now_iso: str) -> list[Suggestion]:
    """읽기목록 중 READING_STALE_DAYS일+ 안 본 미읽음 항목 → reading_stale 후보."""
    now_d = _parse_date(now_iso)
    if now_d is None:
        return []
    stale: list[tuple[dict, int]] = []
    for item in queue:
        if not isinstance(item, dict) or item.get("read"):
            continue
        added = _parse_date(str(item.get("added_at", "")))
        if added is None:
            continue
        age = (now_d - added).days
        if age >= READING_STALE_DAYS:
            stale.append((item, age))
    if not stale:
        return []
    stale.sort(key=lambda x: -x[1])
    oldest, oldest_age = stale[0]
    title = str(oldest.get("title", "(제목없음)"))
    return [
        Suggestion(
            id=f"{now_iso[:10]}:{slot}:reading_stale:0",
            category="reading_stale",
            scope="personal",
            title=f"읽기목록 {len(stale)}건 {oldest_age // 7}주+ 방치",
            why=f"'{title[:50]}' 등 {len(stale)}건이 {READING_STALE_DAYS}일+ 안 읽힘",
            signal_key=f"reading_stale::{title}",
            score=READING_SCORE,
            action_hint="안 본 읽기목록 핵심 요약 제안",
            created_at=now_iso,
            slot=slot,
            status="proposed",
        )
    ]


def pattern_suggestions(edith_home: Path, slot: str, now_iso: str) -> list[Suggestion]:
    """반복 task 패턴 → 자동 실행 없는 한 줄 nudge."""
    from harness.patterns import list_patterns

    out: list[Suggestion] = []
    day = now_iso[:10]
    for idx, pattern in enumerate(list_patterns(edith_home, min_support=3)):
        if pattern.level != "suggest":
            continue
        out.append(
            Suggestion(
                id=f"{day}:{slot}:recurring_pattern:{idx}",
                category="recurring_pattern",
                scope="personal",
                title=f"🔁 늘 하시던 {pattern.label}",
                why=f"최근 trace에서 비슷한 task가 {pattern.support}회 반복됨",
                signal_key=f"recurring_pattern::{pattern.label}",
                score=2.5,
                action_hint=None,
                created_at=now_iso,
                slot=slot,
                status="proposed",
            )
        )
    return out


def _collect_from_signals(signals: dict, slot: str, now_iso: str) -> list[Suggestion]:
    """signals dict(mail_summary/today/digest/health/reading) → 전체 후보."""
    out: list[Suggestion] = []
    out += urgent_mail_suggestions(signals.get("mail_summary") or {}, slot, now_iso)
    out += calendar_conflict_suggestions(signals.get("today") or {}, slot, now_iso)
    out += digest_suggestions(signals.get("digest") or {}, slot, now_iso)
    out += health_suggestions(signals.get("health") or {}, slot, now_iso)
    out += reading_suggestions(signals.get("reading") or [], slot, now_iso)
    return out


def candidate_summary(signals: dict, slot: str, now_iso: str) -> dict:
    """순수 후보 요약(골든 결정성용). compose_brief 없이 signals만으로 카테고리 집계.

    Returns: {"n": 후보 수, "categories": 정렬된 카테고리 목록}.
    """
    cands = _collect_from_signals(signals, slot, now_iso)
    return {"n": len(cands), "categories": sorted({c.category for c in cands})}


def _load_reading_queue(edith_home: Path) -> list[dict]:
    """raw/reading/queue.json 로드(없으면 []). 형식: [{title,url,added_at,read}]."""
    path = edith_home / "raw" / "reading" / "queue.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


class SuggestionGenerator:
    """compose_brief + 읽기목록 신호 → Suggestion 후보.

    compose_brief가 일정·메일·digest·헬스를 모으고, 읽기목록은 raw/reading에서 읽어
    signals dict로 합친 뒤 _collect_from_signals에 위임한다. now_iso를 compose_brief에
    주입해 일정·헬스의 '오늘' 창을 체크인 시각과 일치시킨다.
    """

    def generate(self, edith_home: Path, slot: str, now_iso: str) -> list[Suggestion]:
        """슬롯에 대한 모든 후보 Suggestion 반환."""
        brief = compose_brief(edith_home, now=_parse_datetime(now_iso))
        signals = {
            "mail_summary": brief.mail_summary,
            "today": brief.today,
            "digest": brief.digest,
            "health": brief.health,
            "reading": _load_reading_queue(edith_home),
        }
        return _collect_from_signals(signals, slot, now_iso) + pattern_suggestions(
            edith_home, slot, now_iso
        )


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


def learn_suppression_preferences(
    feedback: list[dict],
    *,
    base_days: int = DEFAULT_SUPPRESSION_DAYS,
    max_days: int = 42,
) -> dict:
    """Aggregate reject feedback into deterministic suppression strength.

    Returns category/signal reject counts plus the learned suppression window in days.
    Non-reject feedback is ignored.
    """
    category_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    for rec in feedback:
        if rec.get("status") != "rejected":
            continue
        signal = rec.get("signal_key")
        if not isinstance(signal, str) or not signal:
            continue
        category = rec.get("category")
        if not isinstance(category, str) or not category:
            category = _category_from_signal(signal)
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "category_counts": dict(sorted(category_counts.items())),
        "signal_counts": dict(sorted(signal_counts.items())),
        "category_days": {
            k: _suppression_days_for_count(v, base_days, max_days)
            for k, v in sorted(category_counts.items())
        },
        "signal_days": {
            k: _suppression_days_for_count(v, base_days, max_days)
            for k, v in sorted(signal_counts.items())
        },
    }


def _suppression_days_for_count(count: int, base_days: int, max_days: int) -> int:
    return min(max_days, max(base_days, base_days * max(1, count)))


def _category_from_signal(signal_key: str) -> str:
    return signal_key.split("::", 1)[0] if signal_key else ""


def _recent_category_rejections(
    feedback: list[dict], now_iso: str, learned_days: dict[str, int]
) -> set[str]:
    """Categories with reject history inside their learned suppression window."""
    now_d = _parse_date(now_iso)
    out: set[str] = set()
    for rec in feedback:
        if rec.get("status") != "rejected":
            continue
        signal = rec.get("signal_key")
        if not isinstance(signal, str) or not signal:
            continue
        category = rec.get("category")
        if not isinstance(category, str) or not category:
            category = _category_from_signal(signal)
        days = learned_days.get(category)
        at = rec.get("at")
        if not category or days is None or not isinstance(at, str):
            continue
        rec_d = _parse_date(at)
        if rec_d is None or now_d is None or (now_d - rec_d).days <= days:
            out.add(category)
    return out


def _apply_suppression_gate(
    suggestions: list[Suggestion],
    feedback: list[dict],
    now_iso: str,
    suppression_days: int,
) -> tuple[list[Suggestion], int]:
    """최근 reject 된 signal_key 후보 제외. (남은 후보, 억제된 수) 반환."""
    rejected = _recent_rejected_keys(feedback, now_iso, suppression_days)
    learned = learn_suppression_preferences(feedback, base_days=suppression_days)
    category_days = {
        category: days
        for category, days in learned["category_days"].items()
        if learned["category_counts"].get(category, 0) >= 2
    }
    rejected_categories = _recent_category_rejections(
        feedback, now_iso, category_days
    )
    kept: list[Suggestion] = []
    suppressed = 0
    for s in suggestions:
        if s.signal_key in rejected or s.category in rejected_categories:
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


def _parse_datetime(iso: str | None) -> datetime | None:
    """ISO 문자열 → aware/naive datetime. 실패 시 None(→ compose_brief 실시간 fallback)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
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
    path = _harness_dir(edith_home) / _SUGGESTIONS_FILE
    with file_lock(path):
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


def preview_checkin(
    edith_home: Path,
    slot: str,
    now_iso: str | None = None,
    weekday_cap: int = DEFAULT_WEEKDAY_CAP,
    weekend_cap: int = DEFAULT_WEEKEND_CAP,
    suppression_days: int = DEFAULT_SUPPRESSION_DAYS,
) -> dict:
    """run_checkin과 동일 파이프라인이되 상태를 쓰지 않는 읽기 전용 미리보기(데모용).

    push_ledger를 증가시키지 않으므로 반복 호출해도 cap을 소모하지 않는다. cap을 적용해
    잘라내지 않고 억제 후 후보 전체를 score 내림차순으로 반환하며, 오늘 cap 안에 드는 상위
    N개의 id를 would_push로 표시한다(데모에서 "실제로 어디까지 push되나"를 보여주기 위함).

    Returns:
        {"slot", "candidates_n", "suppressed_n", "cap", "ranked": [dict...],
         "would_push": [id...]}.
    """
    now_iso = now_iso or datetime.now(UTC).isoformat()
    candidates = SuggestionGenerator().generate(edith_home, slot, now_iso)
    candidates_n = len(candidates)
    candidates = _apply_atrophy_gate(candidates)
    feedback = _load_feedback(edith_home)
    candidates, suppressed_n = _apply_suppression_gate(
        candidates, feedback, now_iso, suppression_days
    )
    ranked = sorted(candidates, key=lambda s: s.score, reverse=True)
    day = _parse_date(now_iso)
    gate = PushGate(weekday_cap=weekday_cap, weekend_cap=weekend_cap)
    cap = gate.cap_for(day) if day is not None else weekday_cap
    return {
        "slot": slot,
        "candidates_n": candidates_n,
        "suppressed_n": suppressed_n,
        "cap": cap,
        "ranked": [s.to_dict() for s in ranked],
        "would_push": [s.id for s in ranked[:cap]],
    }


__all__ = [
    "ATROPHY_PROTECTED",
    "PushGate",
    "Suggestion",
    "SuggestionGenerator",
    "calendar_conflict_suggestions",
    "candidate_summary",
    "digest_suggestions",
    "health_suggestions",
    "is_atrophy_protected",
    "learn_suppression_preferences",
    "pattern_suggestions",
    "preview_checkin",
    "reading_suggestions",
    "record_feedback",
    "run_checkin",
    "urgent_mail_suggestions",
]
