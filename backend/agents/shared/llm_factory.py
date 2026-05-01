from __future__ import annotations

from core.llm_factory import get_llm


class LLMFactory:
    @staticmethod
    def create(provider: str | None = None, model: str | None = None, temperature: float = 0.2):
        return get_llm(provider=provider, model=model, temperature=temperature, streaming=True)
