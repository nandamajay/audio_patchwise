from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from app.security.runtime_secrets import get_runtime_api_key, get_runtime_provider_model


LEGACY_MODEL_MAP: dict[str, tuple[str, str]] = {
    "gpt-4o": ("qgenie", "gpt-4o"),
    "gpt-5": ("qgenie", "gpt-5"),
    "claude-3-5": ("anthropic", "claude-3-5-sonnet-latest"),
    "claude-sonnet-4-5": ("qgenie", "claude-sonnet-4-5"),
    "claude-3-5-sonnet": ("anthropic", "claude-3-5-sonnet-latest"),
    "qualcomm-internal": ("qgenie", "qgenie-pro"),
    "qgenie-pro": ("qgenie", "qgenie-pro"),
    "mock": ("mock", "local"),
    "local": ("mock", "local"),
    "custom": ("mock", "local"),
}

DEFAULT_MODEL_BY_PROVIDER = {
    "qgenie": "gpt-4o",
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "mock": "local",
}


@dataclass
class LLMRuntime:
    provider: str
    model: str
    enabled: bool
    reason: str
    api_key: str = ""


@dataclass
class LLMLineFix:
    original_line: str
    fixed_line: str
    justification: str


def parse_provider_model(
    llm_provider: str | None,
    llm_model: str | None,
) -> tuple[str, str]:
    provider = (llm_provider or "").strip().lower()
    model = (llm_model or "").strip()
    runtime_provider = ""
    runtime_model = ""

    if "/" in model and not provider:
        head, tail = model.split("/", 1)
        provider = head.strip().lower()
        model = tail.strip()
    elif ":" in model and not provider:
        head, tail = model.split(":", 1)
        provider = head.strip().lower()
        model = tail.strip()

    if not provider and model.lower() in LEGACY_MODEL_MAP:
        provider, mapped_model = LEGACY_MODEL_MAP[model.lower()]
        model = mapped_model

    if not provider:
        runtime_provider, runtime_model = get_runtime_provider_model()
        provider = runtime_provider

    if not model:
        model = runtime_model
        if not model:
            model = os.getenv("LLM_MODEL", "").strip()

    if provider in {"qualcomm"}:
        provider = "qgenie"

    if provider in {"local", "none"}:
        provider = "mock"

    if not provider:
        provider = os.getenv("LLM_PROVIDER", "qgenie").strip().lower()

    if not model:
        model = DEFAULT_MODEL_BY_PROVIDER.get(provider, "local")

    if provider == "mock" and model != "local":
        model = "local"

    return provider, model


def _resolve_api_key(provider: str) -> str:
    runtime_key = get_runtime_api_key(provider)
    if runtime_key:
        return runtime_key

    if provider == "qgenie":
        return (os.getenv("QGENIE_API_KEY") or "").strip()
    if provider == "openai":
        return (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if provider == "anthropic":
        return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    return ""


def build_runtime_from_state(state: dict[str, Any]) -> LLMRuntime:
    provider, model = parse_provider_model(
        state.get("llm_provider") or os.getenv("LLM_PROVIDER"),
        state.get("llm_model") or os.getenv("LLM_MODEL"),
    )

    if provider == "mock":
        return LLMRuntime(
            provider=provider,
            model=model,
            enabled=False,
            reason="mock/local mode",
        )

    if provider not in {"qgenie", "openai", "anthropic"}:
        return LLMRuntime(
            provider="mock",
            model="local",
            enabled=False,
            reason=f"unsupported provider '{provider}', using local heuristics",
        )

    api_key = _resolve_api_key(provider)
    if not api_key:
        return LLMRuntime(
            provider=provider,
            model=model,
            enabled=False,
            reason=f"missing API key for provider '{provider}'",
        )

    return LLMRuntime(
        provider=provider,
        model=model,
        enabled=True,
        reason="remote llm enabled",
        api_key=api_key,
    )


def _build_chat_client(runtime: LLMRuntime):
    if not runtime.enabled:
        return None

    if runtime.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=runtime.model,
            api_key=runtime.api_key,
            temperature=0.0,
            max_retries=1,
            timeout=30,
        )

    if runtime.provider == "qgenie":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=runtime.model,
            api_key=runtime.api_key,
            base_url=os.getenv("QGENIE_BASE_URL", "https://qgenie-chat.qualcomm.com/v1"),
            temperature=0.0,
            max_retries=1,
            timeout=30,
        )

    if runtime.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=runtime.model,
            anthropic_api_key=runtime.api_key,
            temperature=0.0,
            max_retries=1,
            timeout=30,
        )

    return None


def _coerce_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def invoke_text(runtime: LLMRuntime, prompt: str) -> str | None:
    if not runtime.enabled:
        return None

    try:
        client = _build_chat_client(runtime)
        if client is None:
            return None
        response = client.invoke(prompt)
        return _coerce_content(getattr(response, "content", response)).strip()
    except Exception:
        return None


def _extract_json_blob(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None

    for opening, closing in (("[", "]"), ("{", "}")):
        start = text.find(opening)
        if start < 0:
            continue
        depth = 0
        for idx in range(start, len(text)):
            ch = text[idx]
            if ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
    return None


def invoke_json(runtime: LLMRuntime, prompt: str) -> Any | None:
    raw = invoke_text(runtime, prompt)
    if not raw:
        return None

    for candidate in (raw, _extract_json_blob(raw)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def parse_line_fix_response(raw: str) -> LLMLineFix | None:
    if not raw:
        return None

    original = ""
    fixed = ""
    justification = ""

    for line in raw.splitlines():
        if line.startswith("ORIGINAL_LINE:"):
            original = line.split(":", 1)[1].strip()
        elif line.startswith("FIXED_LINE:"):
            fixed = line.split(":", 1)[1].strip()
        elif line.startswith("JUSTIFICATION:"):
            justification = line.split(":", 1)[1].strip()

    if not fixed:
        return None

    return LLMLineFix(
        original_line=original,
        fixed_line=fixed,
        justification=justification or "Applied provider-suggested upstream fix.",
    )
