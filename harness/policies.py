"""Policy engine — H5 풀 구현.

`harness/policies.md`의 R1-R5 룰을 코드로 강제.
markdown이 spec, 이 파일이 implementation.
"""

from __future__ import annotations

import re
from typing import Any

from harness.state import Scope

# R1. raw is immutable
IMMUTABLE_RAW_TOOLS: set[str] = {
    "raw_write",
    "raw_delete",
    "raw_modify",
    "raw_truncate",
}

# R2. external write requires approval
EXTERNAL_WRITE_TOOLS: set[str] = {
    "gmail_send",
    "calendar_create",
    "calendar_update",
    "notion_update",
    "github_commit",
    "github_push",
    "slack_send",
    "kakao_send",
}

# R4. PII patterns
PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("kr_mobile", re.compile(r"01[016789]-?\d{3,4}-?\d{4}")),
    ("kr_rrn", re.compile(r"\d{6}-?[1-4]\d{6}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("aws_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
]


def allow(tool: str, args: dict[str, Any], scope: Scope) -> tuple[bool, str | None]:
    """Phase 1+ policy check (R1, R2, R3 강제).

    R4 PII는 별도 `check_external_payload` 함수로.

    Returns:
        (allowed, reason_if_blocked)
    """
    # R1
    if tool in IMMUTABLE_RAW_TOOLS:
        return False, f"R1: raw is immutable — {tool} not allowed (use capture_text)"

    # R2
    if tool in EXTERNAL_WRITE_TOOLS:
        return False, f"R2: {tool} is external write — request_approval required first"

    # R3 — skill scope vs task scope cross-ref.
    # concrete scope(personal/school/work) skill의 tool은 같은 scope task 또는
    # mixed task에서만 허용. (mixed는 "분리 후 각각 처리" — CLAUDE.md scope 룰.)
    from harness.skills import tool_scopes

    skill_scope = tool_scopes().get(tool)
    if skill_scope is not None and skill_scope != "any":
        if scope != "mixed" and scope != skill_scope:
            return False, (
                f"R3: {tool} is {skill_scope}-scoped — blocked in {scope} task "
                f"(cross-scope retrieve 금지)"
            )

    return True, None


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """R4. text 안 PII 패턴을 [REDACTED]로 치환.

    Returns:
        (redacted_text, {pattern_name: count, ...})
    """
    counts: dict[str, int] = {}
    for name, pat in PII_PATTERNS:
        text, k = pat.subn(f"[REDACTED:{name}]", text)
        if k > 0:
            counts[name] = k
    return text, counts


def check_external_payload(text: str) -> tuple[bool, str | None]:
    """R4. 외부 LLM 호출 직전 payload 검사.

    PII 발견 시 차단 (allowed=False, reason). caller가 redact 후 재호출하거나
    사용자 승인을 받아 강제 통과해야 함.
    """
    _, counts = redact_pii(text)
    if counts:
        details = ", ".join(f"{k}×{v}" for k, v in counts.items())
        return False, f"R4: PII detected in payload ({details})"
    return True, None
