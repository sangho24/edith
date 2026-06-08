"""Runtime-editable settings stored outside .env secrets."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.storage import atomic_write_json

SETTINGS_KEYS = (
    "EDITH_LLM",
    "model",
    "EDITH_MAIL_BACKEND",
    "EDITH_CALENDAR_BACKEND",
    "EDITH_MAX_TOKENS",
)
_LLM_CHOICES = {"mock", "anthropic", "gemini", "grok", "groq"}
_MAIL_CHOICES = {"local", "gmail"}
_CALENDAR_CHOICES = {"local", "apple", "google"}
_SECRET_KEYS = (
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "GROQ_API_KEY",
)


@dataclass(frozen=True)
class SettingsUpdate:
    edith_llm: str | None = None
    model: str | None = None
    mail_backend: str | None = None
    calendar_backend: str | None = None
    max_tokens: int | None = None


def settings_path(edith_home: Path) -> Path:
    return edith_home / "harness" / "settings.json"


def load_settings(edith_home: Path) -> dict[str, Any]:
    path = settings_path(edith_home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in SETTINGS_KEYS}


def apply_settings(data: dict[str, Any]) -> None:
    """Apply saved settings to process env so existing runtime code sees them."""
    mapping = {
        "EDITH_LLM": "EDITH_LLM",
        "model": "EDITH_MODEL",
        "EDITH_MAIL_BACKEND": "EDITH_MAIL_BACKEND",
        "EDITH_CALENDAR_BACKEND": "EDITH_CALENDAR_BACKEND",
        "EDITH_MAX_TOKENS": "EDITH_MAX_TOKENS",
    }
    for key, env_key in mapping.items():
        value = data.get(key)
        if value is not None and str(value).strip():
            os.environ[env_key] = str(value).strip()


def load_and_apply_settings(edith_home: Path) -> dict[str, Any]:
    data = load_settings(edith_home)
    apply_settings(data)
    return data


def _effective_value(data: dict[str, Any], key: str, env_key: str, default: str) -> str:
    value = data.get(key)
    if value is not None and str(value).strip():
        return str(value).strip()
    return os.environ.get(env_key, default).strip()


def public_settings(edith_home: Path) -> dict[str, Any]:
    data = load_settings(edith_home)
    return {
        "ok": True,
        "settings": {
            "EDITH_LLM": _effective_value(data, "EDITH_LLM", "EDITH_LLM", ""),
            "model": _effective_value(data, "model", "EDITH_MODEL", ""),
            "EDITH_MAIL_BACKEND": _effective_value(
                data, "EDITH_MAIL_BACKEND", "EDITH_MAIL_BACKEND", ""
            ),
            "EDITH_CALENDAR_BACKEND": _effective_value(
                data, "EDITH_CALENDAR_BACKEND", "EDITH_CALENDAR_BACKEND", ""
            ),
            "EDITH_MAX_TOKENS": _effective_value(
                data, "EDITH_MAX_TOKENS", "EDITH_MAX_TOKENS", "2048"
            ),
        },
        "secrets": {key: bool(os.environ.get(key, "").strip()) for key in _SECRET_KEYS},
    }


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = value.strip()
    return value or None


def parse_settings_update(payload: dict[str, Any]) -> SettingsUpdate:
    edith_llm = _optional_str(payload, "EDITH_LLM")
    if edith_llm is not None:
        edith_llm = edith_llm.lower()
        if edith_llm not in _LLM_CHOICES:
            raise ValueError("EDITH_LLM must be one of anthropic|gemini|grok|groq|mock")

    mail_backend = _optional_str(payload, "EDITH_MAIL_BACKEND")
    if mail_backend is not None:
        mail_backend = mail_backend.lower()
        if mail_backend not in _MAIL_CHOICES:
            raise ValueError("EDITH_MAIL_BACKEND must be one of local|gmail")

    calendar_backend = _optional_str(payload, "EDITH_CALENDAR_BACKEND")
    if calendar_backend is not None:
        calendar_backend = calendar_backend.lower()
        if calendar_backend not in _CALENDAR_CHOICES:
            raise ValueError("EDITH_CALENDAR_BACKEND must be one of local|apple|google")

    max_tokens = None
    if "EDITH_MAX_TOKENS" in payload:
        raw_tokens = payload["EDITH_MAX_TOKENS"]
        if isinstance(raw_tokens, bool):
            raise ValueError("EDITH_MAX_TOKENS must be an integer")
        try:
            max_tokens = int(raw_tokens)
        except (TypeError, ValueError) as e:
            raise ValueError("EDITH_MAX_TOKENS must be an integer") from e
        if max_tokens < 128 or max_tokens > 32768:
            raise ValueError("EDITH_MAX_TOKENS must be between 128 and 32768")

    return SettingsUpdate(
        edith_llm=edith_llm,
        model=_optional_str(payload, "model"),
        mail_backend=mail_backend,
        calendar_backend=calendar_backend,
        max_tokens=max_tokens,
    )


def save_settings(edith_home: Path, update: SettingsUpdate) -> dict[str, Any]:
    current = load_settings(edith_home)
    if update.edith_llm is not None:
        current["EDITH_LLM"] = update.edith_llm
    if update.model is not None:
        current["model"] = update.model
    if update.mail_backend is not None:
        current["EDITH_MAIL_BACKEND"] = update.mail_backend
    if update.calendar_backend is not None:
        current["EDITH_CALENDAR_BACKEND"] = update.calendar_backend
    if update.max_tokens is not None:
        current["EDITH_MAX_TOKENS"] = str(update.max_tokens)

    path = settings_path(edith_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, current)
    apply_settings(current)
    return public_settings(edith_home)
