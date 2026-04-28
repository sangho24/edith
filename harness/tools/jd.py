"""jd_analyze LLM tool — F9. JD vs 본인 이력서 fit 분석 + bullet 제안."""

from __future__ import annotations

from typing import Any

from harness.integrations.jd import analyze_jd, load_resume
from harness.state import Context
from harness.tools import Tool


def _jd_analyze(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    jd_text = args.get("jd_text", "")
    if not jd_text.strip():
        return {"ok": False, "error": "jd_text 필요"}

    resume_text = load_resume(ctx.edith_home)
    if resume_text is None:
        return {
            "ok": False,
            "error": (
                "raw/career/resume.md 가 없습니다. 본인 이력서를 markdown 으로 작성해서 두세요."
            ),
        }

    top_bullets = int(args.get("top_bullets", 5))
    analysis = analyze_jd(jd_text, resume_text, top_bullets=top_bullets)
    return {
        "ok": True,
        "fit_score": round(analysis.fit_score, 2),
        "matched": sorted(analysis.matched),
        "missing": sorted(analysis.missing),
        "n_jd_keywords": len(analysis.jd_keywords),
        "suggested_bullets": analysis.suggested_bullets,
    }


JD_ANALYZE = Tool(
    name="jd_analyze",
    description=(
        "Job Description 텍스트를 받아 raw/career/resume.md 와 fit 분석 + bullet 제안. read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "jd_text": {"type": "string"},
            "top_bullets": {"type": "integer", "default": 5},
        },
        "required": ["jd_text"],
    },
    fn=_jd_analyze,
)
