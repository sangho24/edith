"""skill registry 검증.

- 모든 skill은 tool ≥1개
- tool name은 skill 간 중복 없음
- build_registry()는 17개 tool 등록 (마이그레이션 전 build_default_registry와 동일)
- eval_globs에 선언된 경로는 실재하는 파일을 가리킴 (CLAUDE.md "eval 먼저" 룰 강제)
"""

from __future__ import annotations

from pathlib import Path

from harness.skills import all_skills, build_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_every_skill_has_tools() -> None:
    for skill in all_skills():
        assert skill.tools, f"skill {skill.name} has no tools"


def test_no_duplicate_tool_names_across_skills() -> None:
    seen: dict[str, str] = {}
    for skill in all_skills():
        for tool in skill.tools:
            assert tool.name not in seen, (
                f"tool {tool.name} in both {seen[tool.name]} and {skill.name}"
            )
            seen[tool.name] = skill.name


def test_build_registry_registers_all_17_tools() -> None:
    reg = build_registry()
    assert len(reg.all_specs()) == 17


def test_build_default_registry_delegates_to_skills() -> None:
    from harness.tools import build_default_registry

    assert {s["name"] for s in build_default_registry().all_specs()} == {
        s["name"] for s in build_registry().all_specs()
    }


def test_eval_globs_point_to_existing_files() -> None:
    for skill in all_skills():
        for glob in skill.eval_globs:
            assert (REPO_ROOT / glob).exists(), (
                f"skill {skill.name} declares missing eval: {glob}"
            )


def test_skill_scopes_are_valid() -> None:
    valid = {"personal", "school", "work", "any"}
    for skill in all_skills():
        assert skill.scope in valid, f"skill {skill.name} bad scope: {skill.scope}"
