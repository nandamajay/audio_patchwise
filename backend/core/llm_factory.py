"""
LLM Factory — Provides QGenie-powered LLM instances for CHANAKYA & ARYABHATA.
QGenie is OpenAI-API-compatible, so we use ChatOpenAI with custom base_url.
"""

from __future__ import annotations

import os
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

try:
    from app.security.runtime_secrets import get_runtime_api_key
except Exception:  # pragma: no cover
    def get_runtime_api_key(provider: str) -> str:  # type: ignore[no-redef]
        _ = provider
        return ""


# QGenie supported models
QGENIE_MODELS = {
    "gpt-4o": "GPT-4o via QGenie (Recommended)",
    "gpt-5": "GPT-5 via QGenie (Latest)",
    "claude-sonnet-4-5": "Claude Sonnet 4.5 via QGenie",
    "claude-opus-4": "Claude Opus 4 via QGenie",
    "qgenie-pro": "QGenie Pro (On-Prem, Fast)",
}

EXTERNAL_MODELS = {
    "openai/gpt-4o": "GPT-4o (OpenAI Direct)",
    "anthropic/claude-sonnet-4-5": "Claude Sonnet 4.5 (Anthropic Direct)",
}

ALL_MODELS = {**QGENIE_MODELS, **EXTERNAL_MODELS}


def _normalize_provider(provider: str | None) -> str:
    normalized = (provider or os.getenv("LLM_PROVIDER", "qgenie")).strip().lower()
    if normalized in {"local", "mock", "none"}:
        return "qgenie"
    if normalized in {"qualcomm", "qgenie"}:
        return "qgenie"
    return normalized


def _normalize_model(model: str | None, provider: str) -> str:
    value = (model or os.getenv("LLM_MODEL", "")).strip()
    if "/" in value:
        maybe_provider, maybe_model = value.split("/", 1)
        if maybe_provider.strip().lower() == provider:
            return maybe_model.strip()
    if ":" in value:
        maybe_provider, maybe_model = value.split(":", 1)
        if maybe_provider.strip().lower() == provider:
            return maybe_model.strip()

    if value:
        return value

    if provider == "qgenie":
        return os.getenv("QGENIE_DEFAULT_MODEL", "gpt-4o")
    if provider == "openai":
        return "gpt-4o"
    if provider == "anthropic":
        return "claude-sonnet-4-5"
    return "gpt-4o"


def _resolve_key(provider: str) -> str:
    runtime = get_runtime_api_key(provider)
    if runtime:
        return runtime

    if provider == "qgenie":
        return (os.getenv("QGENIE_API_KEY") or "").strip()
    if provider == "openai":
        return (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if provider == "anthropic":
        return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    return ""


def get_llm(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.1,
    streaming: bool = True,
):
    """
    Returns a LangChain LLM instance.
    Defaults to QGenie as provider for best Qualcomm-internal performance.
    """
    resolved_provider = _normalize_provider(provider)
    resolved_model = _normalize_model(model, resolved_provider)

    if resolved_provider == "qgenie":
        return _get_qgenie_llm(resolved_model, temperature, streaming)
    if resolved_provider == "openai":
        return _get_openai_llm(resolved_model, temperature, streaming)
    if resolved_provider == "anthropic":
        return _get_anthropic_llm(resolved_model, temperature, streaming)

    raise ValueError(f"Unknown LLM provider: {resolved_provider}")


def _get_qgenie_llm(model: str, temperature: float, streaming: bool) -> ChatOpenAI:
    """QGenie is OpenAI-API-compatible and is the recommended provider."""
    api_key = _resolve_key("qgenie")
    base_url = os.getenv("QGENIE_BASE_URL", "https://qgenie-chat.qualcomm.com/v1")

    if not api_key:
        raise EnvironmentError(
            "QGENIE_API_KEY is not set. Configure it in .env or via /settings runtime key store."
        )

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        streaming=streaming,
        timeout=120,
        max_retries=3,
    )


def _get_openai_llm(model: str, temperature: float, streaming: bool) -> ChatOpenAI:
    """Direct OpenAI — fallback only."""
    api_key = _resolve_key("openai")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature,
        streaming=streaming,
        timeout=120,
        max_retries=3,
    )


def _get_anthropic_llm(model: str, temperature: float, streaming: bool) -> ChatAnthropic:
    """Direct Anthropic — fallback only."""
    api_key = _resolve_key("anthropic")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set")
    return ChatAnthropic(
        model=model,
        api_key=api_key,
        temperature=temperature,
        streaming=streaming,
        timeout=120,
        max_retries=3,
    )


def get_available_models() -> dict:
    """Returns all available models for the UI dropdown, QGenie first."""
    provider = _normalize_provider(os.getenv("LLM_PROVIDER", "qgenie"))
    qgenie_key = _resolve_key("qgenie")
    openai_key = _resolve_key("openai")
    anthropic_key = _resolve_key("anthropic")

    models: list[dict] = []

    if qgenie_key:
        for model_id, label in QGENIE_MODELS.items():
            models.append(
                {
                    "id": model_id,
                    "label": label,
                    "provider": "qgenie",
                    "recommended": model_id == "gpt-4o",
                    "badge": "🔵 QGenie",
                }
            )

    if openai_key:
        models.append(
            {
                "id": "gpt-4o",
                "label": "GPT-4o (OpenAI Direct)",
                "provider": "openai",
                "recommended": False,
                "badge": "🟢 OpenAI",
            }
        )

    if anthropic_key:
        models.append(
            {
                "id": "claude-sonnet-4-5",
                "label": "Claude Sonnet 4.5 (Anthropic Direct)",
                "provider": "anthropic",
                "recommended": False,
                "badge": "🟠 Anthropic",
            }
        )

    if not models:
        # Keep UI usable even before keys are configured.
        models = [
            {
                "id": "gpt-4o",
                "label": "GPT-4o via QGenie (Recommended)",
                "provider": "qgenie",
                "recommended": True,
                "badge": "🔵 QGenie",
            }
        ]

    return {
        "models": models,
        "default": os.getenv("QGENIE_DEFAULT_MODEL", "gpt-4o"),
        "active_provider": provider,
    }
