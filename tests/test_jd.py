"""Phase 3 F9 — JD analyzer tests."""

from __future__ import annotations

from pathlib import Path

from harness.integrations.jd import (
    analyze_jd,
    extract_keywords,
    extract_required_keywords,
    load_resume,
)

# ── extract_keywords ──


def test_extract_python_react() -> None:
    text = "We use Python, React, and PostgreSQL daily."
    kws = extract_keywords(text)
    assert "python" in kws
    assert "react" in kws
    assert "postgresql" in kws


def test_extract_case_insensitive() -> None:
    text = "PYTHON developer needed"
    assert "python" in extract_keywords(text)


def test_extract_returns_empty_for_unrelated() -> None:
    text = "Looking for someone who likes coffee"
    assert extract_keywords(text) == set()


def test_extract_pytorch_transformers() -> None:
    text = "experience with pytorch, huggingface transformers, fine-tuning LLM"
    kws = extract_keywords(text)
    assert "pytorch" in kws
    assert "huggingface" in kws
    assert "transformers" in kws
    assert "fine-tuning" in kws
    assert "llm" in kws


def test_extract_required_alias_for_now() -> None:
    """Phase 3 MVP: required = all keywords."""
    text = "Required: Python, React. Nice-to-have: Rust"
    req = extract_required_keywords(text)
    assert "python" in req
    assert "react" in req
    assert "rust" in req  # MVP에선 구분 안 함


# ── analyze_jd ──


JD_ML = """We are looking for a Senior ML Engineer.

Required:
- Python (3+ years)
- PyTorch or TensorFlow
- LLM fine-tuning experience
- Docker and Kubernetes
- AWS or GCP

Nice to have:
- Go
- Rust
"""

RESUME_GOOD = """# 상호 — AI Scientist

## 경험
- Python 5년, PyTorch 3년
- LLM fine-tuning (Llama, Solar)
- Docker · Kubernetes · AWS 운영
- transformer interpretability 연구

## 학력
- 컴퓨터공학 학사
"""

RESUME_PARTIAL = """# 상호

## 경험
- Python 5년
- React frontend 1년
"""


def test_high_fit_score() -> None:
    a = analyze_jd(JD_ML, RESUME_GOOD)
    # 11개 JD keyword 중 7개 매치 (tensorflow/gcp/go/rust 빠짐) → 0.636
    assert a.fit_score >= 0.6
    assert "python" in a.matched
    assert "pytorch" in a.matched
    assert "docker" in a.matched
    assert "kubernetes" in a.matched
    assert "aws" in a.matched
    assert "llm" in a.matched


def test_low_fit_score() -> None:
    a = analyze_jd(JD_ML, RESUME_PARTIAL)
    assert a.fit_score < 0.5
    assert "python" in a.matched
    # PyTorch 없으니 missing
    assert "pytorch" in a.missing


def test_bullet_suggestion() -> None:
    a = analyze_jd(JD_ML, RESUME_GOOD)
    assert len(a.suggested_bullets) > 0
    bullets_lower = " ".join(a.suggested_bullets).lower()
    # 매치된 키워드 중 하나는 bullet에 포함되어야
    assert any(kw in bullets_lower for kw in ["python", "pytorch", "docker"])


def test_render_text() -> None:
    a = analyze_jd(JD_ML, RESUME_GOOD)
    text = a.render_text()
    assert "fit score" in text
    assert "%" in text
    assert "매칭" in text


# ── load_resume ──


def test_load_resume_missing(tmp_path: Path) -> None:
    assert load_resume(tmp_path) is None


def test_load_resume_present(tmp_path: Path) -> None:
    (tmp_path / "raw" / "career").mkdir(parents=True)
    (tmp_path / "raw" / "career" / "resume.md").write_text("# Me", encoding="utf-8")
    assert load_resume(tmp_path) == "# Me"


def test_jd_5_sample_accuracy() -> None:
    """5개 mock JD에 대해 RESUME_GOOD으로 fit_score 합리적인지."""
    jds = [
        ("Python ML role", JD_ML, 0.5),
        (
            "Pure frontend (React only)",
            "We need React, TypeScript, Next.js",
            0.0,
        ),  # RESUME에는 react 없음
        ("Backend Python+Postgres", "Python, PostgreSQL, FastAPI required", 0.3),
        ("Devops AWS+K8s", "AWS, Kubernetes, Docker, Terraform expert", 0.7),
        ("ML researcher", "PyTorch, transformers, fine-tuning, LLM", 0.7),
    ]
    for _name, jd_text, expected_min in jds:
        a = analyze_jd(jd_text, RESUME_GOOD)
        assert a.fit_score >= expected_min, f"{_name}: fit {a.fit_score:.2f} < {expected_min:.2f}"
