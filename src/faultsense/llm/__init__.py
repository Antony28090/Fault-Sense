"""LLM providers behind a small interface; the provider and model come from Settings."""
from __future__ import annotations

from faultsense.config import Settings
from faultsense.llm.base import LLMProvider


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from faultsense.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.llm_model, settings.llm_api_key, settings.llm_effort)
    if settings.llm_provider == "ollama":
        from faultsense.llm.ollama_provider import OllamaProvider

        return OllamaProvider(settings.llm_model, settings.ollama_url, settings.ollama_num_ctx, settings.ollama_think)
    raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}")
