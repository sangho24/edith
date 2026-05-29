"""Phase 3 F4 / Phase 4 B3 — Morning Briefing.

매일 08시 (or 사용자 설정) 한 화면 brief:
- 오늘 일정 (F2)
- 메일 priority (F3)
- ds-digest 최근 (F4 — GitHub Pages도 지원)
- 헬스 요약 (F15 — Apple Health)
- Top 3 (rule-based 합성)

Push 채널: 카톡 메모 (KakaoTalk Talk Memo API) 또는 이메일. 지금은 stdout/CLI.
실제 push 통합은 F4.x (KakaoTalk) / F4.y (email).
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from harness.calendar import select_source, today_view
from harness.integrations.apple_health import daily_summary, format_for_brief, get_health_source
from harness.integrations.ds_digest import LocalDigestSource, get_digest_source
from harness.mail import LocalMessageSource, triage


@dataclass
class MorningBrief:
    today_str: str
    today: dict = field(
        default_factory=lambda: {"n_events": 0, "events": [], "total_busy_minutes": 0}
    )
    mail_summary: dict = field(
        default_factory=lambda: {"n_unread": 0, "by_priority": {}, "urgent": [], "important": []}
    )
    digest: dict = field(default_factory=lambda: {"date": None, "items": [], "n": 0})
    health: dict = field(default_factory=dict)
    top3: list[str] = field(default_factory=list)

    def render_text(self) -> str:
        lines = [
            "─" * 50,
            f"☀️ Edith · {self.today_str}",
            "─" * 50,
        ]

        # Top 3
        if self.top3:
            lines.append("Top 3:")
            for t in self.top3:
                lines.append(f"  • {t}")
            lines.append("")

        # 일정
        n_ev = self.today["n_events"]
        if n_ev:
            busy = self.today["total_busy_minutes"]
            lines.append(f"📅 일정 {n_ev}건 · {busy}분 ({busy / 60:.1f}h)")
            for ev in self.today["events"][:5]:
                lines.append(f"   {ev['summary']}")
            if n_ev > 5:
                lines.append(f"   ... +{n_ev - 5}건")
        else:
            lines.append("📅 일정: 없음")
        lines.append("")

        # 메일
        n_mail = self.mail_summary["n_unread"]
        if n_mail:
            counts = self.mail_summary["by_priority"]
            counts_str = " · ".join(f"{k}={v}" for k, v in counts.items() if v)
            lines.append(f"📧 unread {n_mail}건 · {counts_str}")
            for s in self.mail_summary["urgent"][:3]:
                lines.append(f"   ❗ {s}")
            for s in self.mail_summary["important"][:2]:
                lines.append(f"   ★ {s}")
        else:
            lines.append("📧 unread 메일: 없음")
        lines.append("")

        # ds-digest
        n_dig = self.digest["n"]
        if n_dig:
            lines.append(f"📰 ds-digest {n_dig}건 · {self.digest['date']}")
            for item in self.digest["items"][:3]:
                lines.append(f"   · {item['title'][:80]}")
        else:
            lines.append("📰 ds-digest: (오늘 결과 없음)")
        lines.append("")

        # 헬스 (F15)
        if self.health:
            lines.append(f"🩺 {format_for_brief(self.health)}")
        else:
            lines.append("🩺 헬스 데이터: 없음")

        return "\n".join(lines)


def _build_top3(today: dict, mail_summary: dict, digest: dict) -> list[str]:
    """rule-based Top 3 — urgent 메일 1개 + 첫 일정 2개 + digest 첫 1개. 부족하면 채워짐."""
    top3: list[str] = []

    for s in mail_summary["urgent"][:1]:
        top3.append(f"📧 urgent: {s[:60]}")

    for ev in today["events"][:2]:
        top3.append(f"📅 {ev['summary']}")

    if digest["items"] and len(top3) < 3:
        top3.append(f"📰 {digest['items'][0]['title'][:60]}")

    # 부족하면 important 메일로 채움
    for s in mail_summary["important"][:3]:
        if len(top3) >= 3:
            break
        top3.append(f"📧 {s[:60]}")

    return top3[:3]


def compose_brief(edith_home: Path, now: datetime | None = None) -> MorningBrief:
    """오늘 brief 합성 (no LLM).

    now 주입 시 일정·헬스의 '오늘' 창을 그 시각 기준으로 잡는다(데모/체크인 결정성).
    now=None이면 기존과 동일하게 실시간(UTC now / date.today())을 쓴다.
    """
    ref = now or datetime.now(UTC)
    today_str = ref.strftime("%Y-%m-%d (%a)")
    brief = MorningBrief(today_str=today_str)

    # 1. 일정 — macOS 면 EventKit, 아니면 LocalCalendarSource (fixture/json)
    fixture_env = os.environ.get("EDITH_CALENDAR_FIXTURE")
    cal_source = select_source(
        edith_home=edith_home,
        fixture_path=Path(fixture_env) if fixture_env else None,
    )
    brief.today = today_view(cal_source, now)

    # 2. 메일
    mail_path = Path(
        os.environ.get("EDITH_MAIL_FIXTURE") or (edith_home / "raw" / "mail" / "messages.json")
    )
    items = triage(LocalMessageSource(mail_path).list_unread())
    counts = Counter(i.priority for i in items)
    brief.mail_summary = {
        "n_unread": len(items),
        "by_priority": dict(counts),
        "urgent": [i.message.subject for i in items if i.priority == "urgent"],
        "important": [i.message.subject for i in items if i.priority == "important"],
    }

    # 3. ds-digest — 명시적 로컬 경로(EDITH_DS_DIGEST_LATEST) 우선,
    #    아니면 get_digest_source (EDITH_DS_DIGEST_URL 있으면 GitHub Pages).
    fixture_env = os.environ.get("EDITH_DS_DIGEST_LATEST")
    if fixture_env:
        brief.digest = LocalDigestSource(Path(fixture_env)).latest()
    else:
        brief.digest = get_digest_source(edith_home).latest()

    # 4. 헬스 (F15) — 오늘치 Apple Health 요약.
    #    now 명시 시 '오늘'을 Edith 시간대(KST)로 통일(일정 창과 일치). None이면 기존 date.today().
    if now is not None:
        from harness.localtime import edith_today

        today_d = edith_today(now)
    else:
        today_d = date.today()
    samples = get_health_source(edith_home).samples(today_d, today_d)
    brief.health = daily_summary(samples, today_d)

    # 5. Top 3
    brief.top3 = _build_top3(brief.today, brief.mail_summary, brief.digest)

    return brief
