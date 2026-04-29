"""H1 — Runtime Loop.

input → action → observation → repeat (with budget).
모든 step이 trace에 기록되고 JSONL로 저장.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from harness import policies
from harness.llm import AnthropicLLM, GeminiLLM, GrokLLM, MockLLM, get_llm
from harness.state import Budget, Context, Scope, Trace
from harness.tools import Registry, build_default_registry


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run(
    task: str,
    edith_home: Path,
    scope: Scope = "personal",
    budget: Budget | None = None,
    registry: Registry | None = None,
    llm: AnthropicLLM | GeminiLLM | GrokLLM | MockLLM | None = None,
) -> Trace:
    """한 task을 LLM + tools로 실행. 모든 step이 trace에 기록됨."""
    budget = budget or Budget()
    registry = registry or build_default_registry()
    llm = llm or get_llm()

    identity = _load_text(edith_home / "identity.md")
    schema = _load_text(edith_home / "CLAUDE.md")
    system_prompt = f"{identity}\n\n---\n\n{schema}"

    trace = Trace.start(task, scope=scope)
    ctx = Context(edith_home=edith_home, scope=scope, trace=trace)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    tools_spec = registry.all_specs()
    started = time.time()

    while True:
        # 종료 조건 체크 (각 loop iteration 시작에서)
        if trace.cost_tokens >= budget.max_tokens:
            trace.finalize_reason = "budget_tokens"
            trace.record("finalize", reason="budget_tokens", cost=trace.cost_tokens)
            break
        if trace.n_steps >= budget.max_steps:
            trace.finalize_reason = "budget_steps"
            trace.record("finalize", reason="budget_steps", steps=trace.n_steps)
            break
        if (time.time() - started) > budget.max_seconds:
            trace.finalize_reason = "budget_time"
            trace.record("finalize", reason="budget_time")
            break

        # LLM 호출
        trace.record("llm_call", n_messages=len(messages))
        try:
            resp = llm.call(messages=messages, tools=tools_spec, system=system_prompt)
        except Exception as e:
            trace.finalize_reason = "error"
            trace.record("error", where="llm_call", msg=str(e))
            break

        trace.cost_tokens += resp.usage_in + resp.usage_out
        trace.n_steps += 1

        # end_turn — 정상 종료
        if resp.stop_reason == "end_turn":
            trace.output = resp.text
            trace.finalize_reason = "end_turn"
            trace.record("finalize", reason="end_turn", out_len=len(resp.text))
            break

        # tool_use — 각 tool 호출
        if resp.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            for block in resp.content_blocks:
                if block.get("type") != "tool_use":
                    continue
                name = block["name"]
                args = block["input"]
                tu_id = block["id"]
                trace.record("action", tool=name, args=args, id=tu_id)

                allowed, reason = policies.allow(name, args, scope=ctx.scope)
                if not allowed:
                    trace.record("blocked", tool=name, reason=reason)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu_id,
                            "is_error": True,
                            "content": f"policy blocked: {reason}",
                        }
                    )
                    continue

                t0 = time.time()
                try:
                    result = registry.execute(name, args, ctx)
                    latency_ms = (time.time() - t0) * 1000
                    trace.record(
                        "observation",
                        tool=name,
                        result=result,
                        latency_ms=round(latency_ms, 1),
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu_id,
                            "content": str(result),
                        }
                    )
                except Exception as e:
                    trace.record("error", where=f"tool:{name}", msg=str(e))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu_id,
                            "is_error": True,
                            "content": f"tool error: {e}",
                        }
                    )

            messages.append({"role": "assistant", "content": resp.content_blocks})
            messages.append({"role": "user", "content": tool_results})
            continue

        # 알 수 없는 stop_reason
        trace.finalize_reason = "unknown_stop"
        trace.record("finalize", reason=f"stop:{resp.stop_reason}")
        break

    # trace 자동 저장
    trace.save(edith_home / "harness" / "traces")
    return trace
