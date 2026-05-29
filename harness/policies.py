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

    # F23 — propose_workflow 우회 차단.
    # propose_workflow는 "internal write"라 자동 허용되지만, step.params에 외부 write
    # 액션·PII를 담으면 R2/R3/R4를 우회 통과한다. propose 시점에 각 step을 재귀 검사한다.
    if tool in PROPOSAL_TOOLS:
        ok, reason = check_proposal_steps(args.get("steps", []), scope)
        if not ok:
            return False, reason

    return True, None


# F23 — step 묶음(워크플로우 제안)을 만드는 tool. 이들의 args.steps는 재귀 검사 대상.
PROPOSAL_TOOLS: set[str] = {"propose_workflow"}


def register_external_write_tool(name: str) -> None:
    """동적 tool(MCP 등)을 R2 대상에 등록 (F23). F29 MCP external-write tool용.

    make_mcp_tool가 만든 동적 tool 이름은 정적 EXTERNAL_WRITE_TOOLS에 없어 R2를
    우회한다. external-write MCP tool 등록 시 이 함수로 R2 대상에 추가하고,
    skills.tool_scopes 캐시도 무효화해야 한다(invalidate_tool_scopes_cache).
    """
    EXTERNAL_WRITE_TOOLS.add(name)


def invalidate_tool_scopes_cache() -> None:
    """skills.tool_scopes lru_cache 무효화 (동적 tool 등록 후 R3 반영)."""
    from harness.skills import tool_scopes

    tool_scopes.cache_clear()


def check_proposal_steps(
    steps: list[dict[str, Any]], task_scope: Scope
) -> tuple[bool, str | None]:
    """F23 — 워크플로우 제안의 각 step을 검사. 우회 방지(defense-in-depth).

    - R3: step.scope가 concrete면 task_scope와 일치해야(또는 task가 mixed). 다른 scope의
      액션을 한 제안에 섞지 못하게 한다.
    - R4: step.params 안 문자열에 PII가 있으면 차단 (제안에 PII가 영속 저장되는 것 방지).

    external-write action_type 자체는 허용한다 — 제안은 accept 시 step별로 ApprovalQueue를
    거쳐 실행되므로 R2는 그때 작동. propose 시점엔 scope·PII만 막는다.
    """
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"F23: step[{i}]이 dict가 아님"
        step_scope = step.get("scope")
        if step_scope in ("personal", "school", "work"):
            if task_scope != "mixed" and step_scope != task_scope:
                return False, (
                    f"F23/R3: step[{i}] scope={step_scope} ≠ task scope={task_scope} "
                    f"— cross-scope 제안 차단"
                )
        # params 안 문자열을 직렬화해 PII 검사
        params = step.get("params", {})
        blob = " ".join(str(v) for v in _flatten_strings(params))
        ok, reason = check_external_payload(blob)
        if not ok:
            return False, f"F23/R4: step[{i}] params에 PII — {reason}"
    return True, None


def _flatten_strings(value: Any) -> list[str]:
    """중첩 dict/list에서 문자열 값만 모은다 (PII 검사용)."""
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            out += _flatten_strings(v)
    elif isinstance(value, list):
        for v in value:
            out += _flatten_strings(v)
    return out


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


def guard_outbound(text: str) -> dict[str, Any]:
    """R5 (F24, PRD docs/08 §4.8). 발신측 PII 게이트 — `Channel.send` 직전 chokepoint.

    R4 `check_external_payload`를 send-side 의미로 래핑한 이름 명확화 진입점이다.
    외부로 나가는 텍스트(Telegram·Mock 등 모든 채널 send)는 이 게이트를 통과해야 한다.
    PII(이메일/전화/주민번호/API key) 발견 시 ok=False로 전송 차단.

    기존 `check_external_payload` 시그니처는 하위호환 위해 그대로 두고, golden
    kind:call의 `returns_contains` 단언이 깔끔하도록 dict를 반환한다.

    Returns:
        {"ok": bool, "reason": str | None} — ok=False면 reason에 탐지 내역.
    """
    allowed, reason = check_external_payload(text)
    return {"ok": allowed, "reason": reason}
