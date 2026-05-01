from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.llm_bridge import parse_provider_model
from app.security.runtime_secrets import (
    load_runtime_llm_settings,
    mask_secret,
    save_runtime_llm_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class LLMSettingsRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    api_key: str = Field(default="")
    key_provider: str | None = None
    clear_key: bool = False
    persist_runtime: bool = True


class LLMSettingsResponse(BaseModel):
    llm_provider: str
    llm_model: str
    key_source: Literal["runtime", "env", "none"]
    keys_present: dict[str, bool]
    key_masked: str


def _env_key_for_provider(provider: str) -> str:
    if provider == "openai":
        return (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if provider == "anthropic":
        return (os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if provider == "qualcomm":
        return (os.getenv("QUALCOMM_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    return ""


def _response_payload(provider: str, model: str) -> LLMSettingsResponse:
    runtime = load_runtime_llm_settings()
    runtime_keys = runtime.get("keys", {}) if isinstance(runtime.get("keys", {}), dict) else {}

    provider_key = str(runtime_keys.get(provider, "") or "")
    key_source: Literal["runtime", "env", "none"] = "none"
    effective_key = ""

    if provider_key:
        key_source = "runtime"
        effective_key = provider_key
    else:
        env_key = _env_key_for_provider(provider)
        if env_key:
            key_source = "env"
            effective_key = env_key

    return LLMSettingsResponse(
        llm_provider=provider,
        llm_model=model,
        key_source=key_source,
        keys_present={
            "openai": bool(runtime_keys.get("openai")) or bool(_env_key_for_provider("openai")),
            "anthropic": bool(runtime_keys.get("anthropic"))
            or bool(_env_key_for_provider("anthropic")),
            "qualcomm": bool(runtime_keys.get("qualcomm")) or bool(_env_key_for_provider("qualcomm")),
        },
        key_masked=mask_secret(effective_key),
    )


@router.get("/llm", response_model=LLMSettingsResponse)
def get_llm_settings() -> LLMSettingsResponse:
    runtime = load_runtime_llm_settings()
    provider, model = parse_provider_model(
        runtime.get("llm_provider") or os.getenv("LLM_PROVIDER"),
        runtime.get("llm_model") or os.getenv("LLM_MODEL"),
    )
    return _response_payload(provider, model)


@router.post("/llm", response_model=LLMSettingsResponse)
def set_llm_settings(payload: LLMSettingsRequest) -> LLMSettingsResponse:
    current = load_runtime_llm_settings()
    provider = payload.llm_provider or current.get("llm_provider") or os.getenv("LLM_PROVIDER")
    model = payload.llm_model or current.get("llm_model") or os.getenv("LLM_MODEL")
    provider, model = parse_provider_model(provider, model)

    if payload.persist_runtime:
        save_runtime_llm_settings(
            llm_provider=provider,
            llm_model=model,
            key_provider=payload.key_provider or provider,
            api_key=payload.api_key,
            clear_key=payload.clear_key,
        )

    return _response_payload(provider, model)
