"""Phase 3 F9 — JD Analyzer.

JD (Job Description) 텍스트를 받아 본인 이력서와 fit 분석 + bullet 제안.

실제 사용 흐름:
1. 사용자 이력서를 raw/career/resume.md 에 markdown 으로 둔다 (본인이 한 번 작성).
2. JD URL 또는 텍스트를 분석 대상으로 던진다.
3. fit_score 계산 + bullet 제안.

heuristic (no LLM, MVP):
- 키워드 매칭: JD에서 추출한 키워드 vs 이력서 키워드
- fit_score = matched / total_required (0.0-1.0)
- bullet 제안: 매칭된 키워드별로 이력서에서 관련 라인 추출
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# JD에서 자주 등장하는 기술 키워드 (확장 가능)
TECH_KEYWORDS = {
    # languages
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "kotlin",
    "swift",
    "c++",
    "ruby",
    "scala",
    # frameworks
    "react",
    "vue",
    "django",
    "flask",
    "fastapi",
    "nextjs",
    "spring",
    "rails",
    "pytorch",
    "tensorflow",
    "jax",
    "huggingface",
    "transformers",
    # ml/ai
    "llm",
    "rag",
    "embedding",
    "fine-tuning",
    "transformer",
    "interpretability",
    "computer vision",
    "nlp",
    "reinforcement learning",
    # infra
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "terraform",
    "ci/cd",
    "github actions",
    # data
    "sql",
    "postgresql",
    "redis",
    "mongodb",
    "snowflake",
    "bigquery",
    "dbt",
    "airflow",
    "spark",
    # other
    "git",
    "linux",
    "rest api",
    "graphql",
    "microservices",
}


def extract_keywords(text: str) -> set[str]:
    """text에서 TECH_KEYWORDS 매치 (대소문자 무관, single-word는 word-boundary)."""
    low = text.lower()
    out: set[str] = set()
    for kw in TECH_KEYWORDS:
        if " " in kw or "-" in kw or "/" in kw or "+" in kw:
            # multi-word / hyphenated → substring 매치
            if kw in low:
                out.add(kw)
        else:
            # single word → word boundary로 'sql' in 'postgresql' 같은 false positive 방지
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b")
            if pattern.search(low):
                out.add(kw)
    return out


def extract_required_keywords(jd_text: str) -> set[str]:
    """JD 안에서 'required', '필수', 'must have' 섹션 근처 키워드 우선.

    naive: 전체 JD에서 키워드 추출 후 'required' / 'must' / '필수' 섹션 근처에 있으면 priority.
    Phase 3 MVP — 일단 전체 JD 키워드 = required로 간주.
    """
    return extract_keywords(jd_text)


@dataclass
class JDAnalysis:
    jd_keywords: set[str]
    matched: set[str]
    missing: set[str]
    fit_score: float  # 0.0-1.0
    suggested_bullets: list[str] = field(default_factory=list)

    def render_text(self) -> str:
        lines = [
            f"fit score: {self.fit_score * 100:.0f}% ({len(self.matched)}/{len(self.jd_keywords)})",
        ]
        if self.matched:
            lines.append(f"매칭: {', '.join(sorted(self.matched))}")
        if self.missing:
            lines.append(f"부족: {', '.join(sorted(self.missing))}")
        if self.suggested_bullets:
            lines.append("")
            lines.append("제안 bullet:")
            for b in self.suggested_bullets:
                lines.append(f"  • {b}")
        return "\n".join(lines)


def _extract_resume_bullets(resume_text: str, keyword: str) -> list[str]:
    """이력서에서 keyword 포함된 라인 추출 (bullet 후보)."""
    out = []
    kw_low = keyword.lower()
    for line in resume_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if kw_low in stripped.lower():
            # bullet 마커 제거
            cleaned = re.sub(r"^[-*•\s]+", "", stripped)
            if cleaned:
                out.append(cleaned[:150])
    return out


def analyze_jd(jd_text: str, resume_text: str, top_bullets: int = 5) -> JDAnalysis:
    jd_kws = extract_required_keywords(jd_text)
    resume_kws = extract_keywords(resume_text)
    matched = jd_kws & resume_kws
    missing = jd_kws - resume_kws
    fit = len(matched) / max(len(jd_kws), 1)

    bullets: list[str] = []
    seen: set[str] = set()
    for kw in sorted(matched):
        for line in _extract_resume_bullets(resume_text, kw):
            if line not in seen:
                bullets.append(line)
                seen.add(line)
                if len(bullets) >= top_bullets:
                    break
        if len(bullets) >= top_bullets:
            break

    return JDAnalysis(
        jd_keywords=jd_kws,
        matched=matched,
        missing=missing,
        fit_score=fit,
        suggested_bullets=bullets,
    )


def load_resume(edith_home: Path) -> str | None:
    """raw/career/resume.md 에서 이력서 로드."""
    p = edith_home / "raw" / "career" / "resume.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")
