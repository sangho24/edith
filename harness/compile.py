"""Phase 2 W1 — LLM Wiki compilation pipeline.

raw/ 안 미컴파일 파일을 찾아서 LLM에게 "wiki에 통합해라" task 위임.
LLM은 CLAUDE.md의 compile 절차에 따라 raw_read → wiki_search/read/write → log.md append.

진행 상태는 harness/compile_log.json 으로 추적 (machine-local, .gitignore).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.llm import AnthropicLLM, MockLLM
from harness.runtime import run as runtime_run
from harness.state import Scope


@dataclass
class CompileResult:
    new_files: list[str] = field(default_factory=list)
    compiled: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (rel, reason)
    duration_ms: float = 0.0

    def render_text(self) -> str:
        lines = [f"new files: {len(self.new_files)}"]
        for f in self.new_files:
            lines.append(f"  {f}")
        if self.compiled:
            lines.append(f"compiled: {len(self.compiled)}")
            for f in self.compiled:
                lines.append(f"  ✓ {f}")
        if self.failed:
            lines.append(f"failed: {len(self.failed)}")
            for f, reason in self.failed:
                lines.append(f"  ✗ {f}: {reason}")
        return "\n".join(lines)


SCOPE_KEYWORDS: dict[Scope, list[str]] = {
    "work": ["work", "client", "samil", "pwc", "ax_node", "사내", "회사", "클라이언트"],
    "school": ["school", "lecture", "syllabus", "강의", "수업", "과제", "학교", "교수"],
}


def infer_scope(rel: str, content: str = "") -> Scope:
    """파일명 + content 휴리스틱으로 scope 추론. 모호하면 personal."""
    haystack = f"{rel} {content[:500]}".lower()
    for scope, keywords in SCOPE_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return scope
    return "personal"


def _load_log(log_path: Path) -> dict[str, Any]:
    if not log_path.exists():
        return {}
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_log(log_path: Path, log: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(log, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def _find_uncompiled(edith_home: Path, log: dict[str, Any]) -> list[str]:
    raw_dir = edith_home / "raw"
    if not raw_dir.exists():
        return []
    out = []
    for f in raw_dir.rglob("*.md"):
        rel = str(f.relative_to(edith_home))
        if rel.endswith("/.gitkeep") or f.name == ".gitkeep":
            continue
        if rel not in log:
            out.append(rel)
    return sorted(out)


def _compile_task(rel: str) -> str:
    return (
        f"raw 파일 `{rel}` 을 wiki/ 에 통합하세요.\n\n"
        f"CLAUDE.md 'compile 절차'를 그대로 따라:\n"
        f"1. raw_read('{rel}')로 source 읽기\n"
        f"2. 등장 entity·concept 추출\n"
        f"3. wiki_search로 관련 기존 페이지 확인\n"
        f"4. wiki_write로 fact append (페이지 없으면 생성, frontmatter는 H7이 자동 처리)\n"
        f"5. 모순 발견 시 wiki/contradictions.md 에 추가\n"
        f"6. wiki/log.md 에 한 줄 append:\n"
        f"   'YYYY-MM-DD HH:MM · raw/{rel} → wiki/<targets> (요약)'\n\n"
        f"마지막에 무엇을 update했는지 한 줄 요약."
    )


def compile_raw(
    edith_home: Path,
    llm: AnthropicLLM | MockLLM | None = None,
    dry_run: bool = False,
) -> CompileResult:
    """raw/ 안 미컴파일 파일 일괄 컴파일."""
    log_path = edith_home / "harness" / "compile_log.json"
    log = _load_log(log_path)
    new_files = _find_uncompiled(edith_home, log)

    result = CompileResult(new_files=new_files)
    if dry_run or not new_files:
        return result

    t0 = time.time()
    for rel in new_files:
        try:
            content = (edith_home / rel).read_text(encoding="utf-8")
        except Exception as e:
            result.failed.append((rel, f"read_error: {e}"))
            continue

        scope = infer_scope(rel, content)
        task = _compile_task(rel)

        try:
            trace = runtime_run(task, edith_home=edith_home, scope=scope, llm=llm)
        except Exception as e:
            result.failed.append((rel, f"runtime_error: {type(e).__name__}: {e}"))
            continue

        if trace.finalize_reason == "end_turn":
            log[rel] = {
                "compiled_at": datetime.now(UTC).isoformat(),
                "trace_id": trace.id,
                "scope": trace.scope,
                "n_steps": trace.n_steps,
                "cost_tokens": trace.cost_tokens,
            }
            result.compiled.append(rel)
        else:
            result.failed.append((rel, f"finalize={trace.finalize_reason}"))

    _save_log(log_path, log)
    result.duration_ms = (time.time() - t0) * 1000
    return result
