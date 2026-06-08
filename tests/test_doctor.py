"""T2.1 — harness doctor diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from harness.doctor import run_diagnostics


def _check(result, name: str):
    return next(check for check in result.checks if check.name == name)


def test_run_diagnostics_reports_missing_items(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("EDITH_HOME", str(tmp_path))
    result = run_diagnostics(tmp_path, env={})

    assert result.ok is False
    assert _check(result, "LLM 설정").ok is False
    assert "EDITH_LLM 없음" in _check(result, "LLM 설정").detail
    assert _check(result, "Google OAuth 토큰").ok is False
    assert _check(result, "EDITH_MAIL_BACKEND").ok is False
    assert _check(result, "EDITH_CALENDAR_BACKEND").ok is False
    assert _check(result, "필수 디렉토리").ok is False
    assert "raw" in _check(result, "필수 디렉토리").detail


def test_run_diagnostics_checks_provider_key_branch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("EDITH_HOME", str(tmp_path))
    for sub in ("raw", "wiki", "harness", "secrets"):
        (tmp_path / sub).mkdir(parents=True)
    (tmp_path / "secrets" / "google_token.json").write_text(
        json.dumps(
            {
                "scopes": [
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/calendar.readonly",
                    "https://www.googleapis.com/auth/calendar.events",
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "EDITH_LLM=gemini\n"
        "EDITH_MAIL_BACKEND=gmail\n"
        "EDITH_CALENDAR_BACKEND=google\n",
        encoding="utf-8",
    )

    missing_key = run_diagnostics(tmp_path, env={})
    assert _check(missing_key, "LLM 설정").ok is False
    assert "GEMINI_API_KEY 없음" in _check(missing_key, "LLM 설정").detail

    with_key = run_diagnostics(tmp_path, env={"GEMINI_API_KEY": "test-key"})
    assert _check(with_key, "LLM 설정").ok is True
    assert _check(with_key, "Google OAuth 토큰").ok is True
    assert _check(with_key, "EDITH_MAIL_BACKEND").ok is True
    assert _check(with_key, "EDITH_CALENDAR_BACKEND").ok is True
    assert _check(with_key, "필수 디렉토리").ok is True


def test_check_llm_unknown_provider_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDITH_HOME", str(tmp_path))
    (tmp_path / ".env").write_text("EDITH_LLM=openai\n", encoding="utf-8")

    result = run_diagnostics(tmp_path, env={"ANTHROPIC_API_KEY": "present"})
    llm = _check(result, "LLM 설정")

    assert llm.ok is False
    assert "지원 안 됨" in llm.detail
    assert "anthropic, gemini, grok, groq, mock" in llm.fix
