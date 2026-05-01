from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_ALLOWED_PROVIDERS = {"openai", "anthropic", "qualcomm", "mock"}
_DEFAULTS = {
    "llm_provider": "mock",
    "llm_model": "local",
    "keys": {
        "openai": "",
        "anthropic": "",
        "qualcomm": "",
    },
}

_LOCK = threading.Lock()


def _secrets_path() -> Path:
    return Path(os.getenv("RUNTIME_SECRETS_PATH", "./data/runtime_secrets.json"))


def _normalize_provider(value: str | None) -> str:
    provider = (value or "mock").strip().lower()
    if provider in {"none", "local"}:
        return "mock"
    if provider not in _ALLOWED_PROVIDERS:
        return "mock"
    return provider


def _normalize_model(value: str | None, provider: str) -> str:
    model = (value or "").strip()
    if model:
        return model
    if provider == "openai":
        return "gpt-4o"
    if provider == "anthropic":
        return "claude-3-5-sonnet-latest"
    if provider == "qualcomm":
        return "qualcomm-internal"
    return "local"


def _empty_payload() -> dict[str, Any]:
    return {
        "llm_provider": _DEFAULTS["llm_provider"],
        "llm_model": _DEFAULTS["llm_model"],
        "keys": dict(_DEFAULTS["keys"]),
    }


def _read_file_unlocked() -> dict[str, Any]:
    path = _secrets_path()
    if not path.exists():
        return _empty_payload()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        payload = _empty_payload()
        payload["llm_provider"] = _normalize_provider(raw.get("llm_provider"))
        payload["llm_model"] = _normalize_model(raw.get("llm_model"), payload["llm_provider"])
        keys = raw.get("keys", {}) if isinstance(raw.get("keys", {}), dict) else {}
        for provider in payload["keys"]:
            payload["keys"][provider] = str(keys.get(provider, "") or "")
        return payload
    except Exception:
        return _empty_payload()


def load_runtime_llm_settings() -> dict[str, Any]:
    with _LOCK:
        return _read_file_unlocked()


def save_runtime_llm_settings(
    llm_provider: str | None = None,
    llm_model: str | None = None,
    key_provider: str | None = None,
    api_key: str | None = None,
    clear_key: bool = False,
) -> dict[str, Any]:
    with _LOCK:
        payload = _read_file_unlocked()

        if llm_provider is not None:
            payload["llm_provider"] = _normalize_provider(llm_provider)

        if llm_model is not None or llm_provider is not None:
            payload["llm_model"] = _normalize_model(llm_model, payload["llm_provider"])

        target_provider = _normalize_provider(key_provider or payload["llm_provider"])
        if target_provider in payload["keys"]:
            if clear_key:
                payload["keys"][target_provider] = ""
            elif api_key is not None:
                normalized = api_key.strip()
                if normalized:
                    payload["keys"][target_provider] = normalized

        path = _secrets_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        tmp_path.replace(path)

        return payload


def get_runtime_provider_model() -> tuple[str, str]:
    settings = load_runtime_llm_settings()
    return settings["llm_provider"], settings["llm_model"]


def get_runtime_api_key(provider: str) -> str:
    normalized = _normalize_provider(provider)
    if normalized == "mock":
        return ""
    settings = load_runtime_llm_settings()
    return str(settings.get("keys", {}).get(normalized, "") or "")


def mask_secret(secret: str) -> str:
    value = (secret or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 6)}{value[-4:]}"
