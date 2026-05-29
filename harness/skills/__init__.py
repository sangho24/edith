"""Skill registry — tool을 설치 가능한 skill 단위로 묶는 선언적 레이어.

OpenClaw의 ClawHub 패턴을 로컬·선언적으로 옮긴 것. 각 skill은 tool 묶음 +
scope + eval glob + (멀티채널 단계에서 쓸) channel 요구사항을 manifest로 선언한다.
build_registry()가 all_skills()를 순회하며 tool을 Registry에 등록한다.

ds-digest·헬스 같은 신규 기능은 harness/skills/<name>.py 추가만으로 끝난다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from harness.tools import Registry, Tool

SkillScope = Literal["personal", "school", "work", "any"]


@dataclass(frozen=True)
class Skill:
    """설치 단위. tool 묶음 + scope + eval glob + 채널 요구사항.

    CLAUDE.md의 "새 feature는 eval YAML 먼저" 룰을 manifest 레벨에서 강제하기 위해
    eval_globs를 둔다. tests/test_skills.py가 glob이 실재하는 파일을 가리키는지 검증.

    scope는 정책 R3(scope cross-ref)의 입력 — concrete scope(personal/school/work)
    skill의 tool은 다른 scope task에서 호출되면 policies.allow()가 차단한다.
    """

    name: str
    scope: SkillScope
    tools: list[Tool]
    eval_globs: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)


def all_skills() -> list[Skill]:
    """등록된 모든 skill. 신규 skill은 여기에 한 줄 추가."""
    from harness.skills import (
        calendar,
        core,
        ds_digest,
        health,
        jd,
        mail,
        mcp_skill,
        papers,
        recall,
        repo,
    )

    return [
        core.SKILL,
        calendar.SKILL,
        mail.SKILL,
        ds_digest.SKILL,
        recall.SKILL,
        papers.SKILL,
        repo.SKILL,
        jd.SKILL,
        health.SKILL,
        mcp_skill.SKILL,
    ]


def build_registry() -> Registry:
    """all_skills()의 모든 tool을 등록한 Registry 반환."""
    reg = Registry()
    for skill in all_skills():
        for tool in skill.tools:
            reg.register(tool)
    return reg


@lru_cache(maxsize=1)
def tool_scopes() -> dict[str, SkillScope]:
    """tool name → 소속 skill의 scope. 정책 R3 enforce용 역인덱스."""
    out: dict[str, SkillScope] = {}
    for skill in all_skills():
        for tool in skill.tools:
            out[tool.name] = skill.scope
    return out
