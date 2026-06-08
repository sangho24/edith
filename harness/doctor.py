"""Onboarding diagnostics for Edith local setup."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROVIDER_KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic API 키를 .env에 추가하세요."),
    "gemini": ("GEMINI_API_KEY", "Google AI Studio의 GEMINI_API_KEY를 .env에 추가하세요."),
    "grok": ("XAI_API_KEY", "xAI 콘솔의 XAI_API_KEY를 .env에 추가하세요."),
    "groq": ("GROQ_API_KEY", "Groq Cloud의 GROQ_API_KEY를 .env에 추가하세요."),
    "mock": ("", "실 LLM 사용 전 EDITH_LLM과 provider API 키를 설정하세요."),
}
_GOOGLE_DEPS = (
    "google.auth",
    "google_auth_oauthlib.flow",
    "googleapiclient.discovery",
)
_REQUIRED_GOOGLE_SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
}


@dataclass(frozen=True)
class DiagnosticCheck:
    """One doctor check rendered by the CLI."""

    name: str
    ok: bool
    detail: str
    fix: str


@dataclass(frozen=True)
class DiagnosticResult:
    """Structured doctor output."""

    edith_home: Path
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from .env without expanding or exposing secrets."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _env_value(key: str, env_file: Mapping[str, str], env: Mapping[str, str]) -> str:
    return env_file.get(key, env.get(key, "")).strip()


def _check_llm(env_file: Mapping[str, str], env: Mapping[str, str]) -> DiagnosticCheck:
    mode = _env_value("EDITH_LLM", env_file, env).lower()
    if not mode:
        return DiagnosticCheck(
            name="LLM 설정",
            ok=False,
            detail="EDITH_LLM 없음",
            fix=".env에 EDITH_LLM=gemini|groq|grok|anthropic 중 하나를 추가하세요.",
        )
    provider = _PROVIDER_KEYS.get(mode)
    if provider is None:
        return DiagnosticCheck(
            name="LLM 설정",
            ok=False,
            detail=f"EDITH_LLM={mode} 지원 안 됨",
            fix="EDITH_LLM 값은 anthropic, gemini, grok, groq, mock 중 하나로 설정하세요.",
        )
    key_name, key_fix = provider
    if not key_name:
        return DiagnosticCheck(
            name="LLM 설정",
            ok=True,
            detail="EDITH_LLM=mock (API 키 불필요)",
            fix="실 LLM 사용 시 EDITH_LLM과 provider API 키를 설정하세요.",
        )
    has_key = bool(_env_value(key_name, env_file, env))
    return DiagnosticCheck(
        name="LLM 설정",
        ok=has_key,
        detail=f"EDITH_LLM={mode}, {key_name} {'설정됨' if has_key else '없음'}",
        fix=key_fix,
    )


def _with_edith_home_for_google_token(edith_home: Path) -> dict[str, Any]:
    """Call google_auth.token_status while keeping the rest of diagnostics home-scoped."""
    from harness.integrations.google_auth import token_status

    old = os.environ.get("EDITH_HOME")
    os.environ["EDITH_HOME"] = str(edith_home)
    try:
        return token_status()
    finally:
        if old is None:
            os.environ.pop("EDITH_HOME", None)
        else:
            os.environ["EDITH_HOME"] = old


def _check_google_token(edith_home: Path) -> DiagnosticCheck:
    status = _with_edith_home_for_google_token(edith_home)
    scopes = set(status.get("scopes") or [])
    missing_scopes = sorted(_REQUIRED_GOOGLE_SCOPES - scopes)
    ok = bool(status.get("token_exists")) and not missing_scopes
    detail = "토큰 있음" if status.get("token_exists") else "토큰 없음"
    if status.get("token_exists"):
        detail += f", scopes {len(scopes)}/{len(_REQUIRED_GOOGLE_SCOPES)}"
    if missing_scopes:
        detail += f", 누락 {len(missing_scopes)}"
    return DiagnosticCheck(
        name="Google OAuth 토큰",
        ok=ok,
        detail=detail,
        fix="`harness oauth google`을 실행하고 Gmail/Calendar scope 동의를 완료하세요.",
    )


def _check_google_deps() -> DiagnosticCheck:
    missing = [mod for mod in _GOOGLE_DEPS if importlib.util.find_spec(mod) is None]
    return DiagnosticCheck(
        name="[google] 의존성",
        ok=not missing,
        detail="import 가능" if not missing else "누락: " + ", ".join(missing),
        fix='`uv pip install -e ".[google]"`로 Google extra 의존성을 설치하세요.',
    )


def _check_kakao(
    edith_home: Path,
    env_file: Mapping[str, str],
    env: Mapping[str, str],
) -> DiagnosticCheck:
    from harness.integrations.kakao import kakao_token_status

    status = kakao_token_status(token_file=edith_home / "secrets" / "kakao_token.json")
    has_key = bool(_env_value("KAKAO_REST_API_KEY", env_file, env))
    has_any = has_key or bool(status.get("token_exists"))
    if not has_any:
        return DiagnosticCheck(
            name="Kakao 설정(선택)",
            ok=True,
            detail="미설정",
            fix=(
                "카카오 push를 쓰려면 docs/11_kakao_setup.md를 따라 "
                "KAKAO_REST_API_KEY와 토큰을 준비하세요."
            ),
        )

    ok = (
        has_key
        and bool(status.get("has_access_token"))
        and bool(status.get("has_refresh_token"))
        and status.get("expired") is not True
    )
    bits = [
        "REST API 키 있음" if has_key else "REST API 키 없음",
        "토큰 있음" if status.get("token_exists") else "토큰 없음",
    ]
    if status.get("token_exists"):
        bits.append("refresh 있음" if status.get("has_refresh_token") else "refresh 없음")
        if status.get("expired") is True:
            bits.append("access 만료")
    return DiagnosticCheck(
        name="Kakao 설정(선택)",
        ok=ok,
        detail=", ".join(bits),
        fix="docs/11_kakao_setup.md를 따라 .env와 secrets/kakao_token.json을 점검하세요.",
    )


def _check_backend(
    key: str,
    env_file: Mapping[str, str],
    env: Mapping[str, str],
    *,
    allowed: set[str],
    default_label: str,
) -> DiagnosticCheck:
    value = _env_value(key, env_file, env)
    if not value:
        return DiagnosticCheck(
            name=key,
            ok=False,
            detail=f"미설정 (기본 {default_label} 사용)",
            fix=f".env에 {key}={next(iter(sorted(allowed)))} 또는 원하는 backend 값을 추가하세요.",
        )
    ok = value.lower() in allowed
    return DiagnosticCheck(
        name=key,
        ok=ok,
        detail=f"{key}={value}",
        fix=f"{key} 값은 {', '.join(sorted(allowed))} 중 하나로 설정하세요.",
    )


def _check_directories(edith_home: Path) -> DiagnosticCheck:
    required = ("raw", "wiki", "harness")
    missing = [name for name in required if not (edith_home / name).is_dir()]
    return DiagnosticCheck(
        name="필수 디렉토리",
        ok=not missing,
        detail="raw/wiki/harness 있음" if not missing else "누락: " + ", ".join(missing),
        fix=(
            "Edith 홈에서 raw/, wiki/, harness/ 디렉토리를 만들거나 "
            "repo 루트를 EDITH_HOME으로 지정하세요."
        ),
    )


def run_diagnostics(
    edith_home: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> DiagnosticResult:
    """Return structured setup diagnostics for a specific Edith home."""
    home = edith_home.resolve()
    env_map = os.environ if env is None else env
    env_file = _read_env_file(home / ".env")
    checks = (
        _check_llm(env_file, env_map),
        _check_google_token(home),
        _check_google_deps(),
        _check_kakao(home, env_file, env_map),
        _check_backend(
            "EDITH_MAIL_BACKEND",
            env_file,
            env_map,
            allowed={"local", "gmail"},
            default_label="local",
        ),
        _check_backend(
            "EDITH_CALENDAR_BACKEND",
            env_file,
            env_map,
            allowed={"local", "google", "apple"},
            default_label="apple/local",
        ),
        _check_directories(home),
    )
    return DiagnosticResult(edith_home=home, checks=checks)
