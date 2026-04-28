"""Phase 3 F1 — Quick Capture.

`harness cap "<text>"` 의 핵심. 두 경로:

1. **direct** (default): scope 자동 분류 후 raw/captures/<ts>_<source>.md 에 직접 저장.
   API 호출 없음. <50ms. 메모를 즉시 안전하게 남기는 1순위 채널.

2. **via_llm** (--via-llm): runtime을 통해 LLM이 capture_text tool 호출.
   trace 기록되고 wiki 즉시 통합 가능. 비용·latency 있음.

Phase 3 후속에서 KakaoTalk 봇이 webhook으로 이 함수를 호출해 카톡 "나에게 보내기" → raw
파이프라인을 완성. 지금은 CLI 경로만.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from harness.compile import infer_scope
from harness.llm import AnthropicLLM, MockLLM
from harness.runtime import run as runtime_run
from harness.state import Scope


@dataclass
class CaptureResult:
    ok: bool
    path: str | None = None
    scope: Scope | None = None
    via_llm: bool = False
    trace_id: str | None = None
    error: str | None = None


def _safe_source(source: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in source) or "manual"


def capture_to_raw(
    text: str,
    edith_home: Path,
    scope: Scope | None = None,
    source: str = "manual",
    via_llm: bool = False,
    llm: AnthropicLLM | MockLLM | None = None,
) -> CaptureResult:
    """user-facing quick capture.

    Args:
        text: 캡처할 텍스트
        edith_home: edith repo root
        scope: 명시 안 하면 infer_scope로 자동
        source: frontmatter source 필드 + 파일명 일부
        via_llm: True면 runtime/LLM 통과 (trace 기록, wiki 즉시 통합 가능)
        llm: via_llm일 때 사용할 LLM (None이면 env의 EDITH_LLM 따라)
    """
    if not text or not text.strip():
        return CaptureResult(ok=False, error="empty text")

    if scope is None:
        scope = infer_scope(rel=f"raw/captures/{source}.md", content=text)

    if via_llm:
        task = f"다음 텍스트를 capture해라: {text}"
        try:
            trace = runtime_run(task, edith_home=edith_home, scope=scope, llm=llm)
        except Exception as e:
            return CaptureResult(ok=False, scope=scope, via_llm=True, error=f"runtime: {e}")
        ok = trace.finalize_reason == "end_turn"
        # 가장 최근 capture 파일 찾기
        captures = sorted(
            (edith_home / "raw" / "captures").glob("*.md"), key=lambda p: p.stat().st_mtime
        )
        last = captures[-1] if captures else None
        return CaptureResult(
            ok=ok,
            path=str(last.relative_to(edith_home)) if last else None,
            scope=scope,
            via_llm=True,
            trace_id=trace.id,
            error=None if ok else f"finalize={trace.finalize_reason}",
        )

    # direct path — 비-LLM, 빠른 저장
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    fname = f"{ts}_{_safe_source(source)}.md"
    path = edith_home / "raw" / "captures" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nsource: {source}\nscope: {scope}\ncaptured_at: {ts}\n---\n\n"
    path.write_text(frontmatter + text, encoding="utf-8")
    return CaptureResult(
        ok=True,
        path=str(path.relative_to(edith_home)),
        scope=scope,
        via_llm=False,
    )
