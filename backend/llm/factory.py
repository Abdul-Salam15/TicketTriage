import os
from functools import lru_cache

from llm.base import LLMProvider
from llm.openai_provider import OpenAIProvider
from llm.anthropic_provider import AnthropicProvider
from llm.gemini_provider import GeminiProvider


@lru_cache(maxsize=None)
def _build_provider(provider_name: str) -> LLMProvider:
    # cached so the underlying SDK client (and its HTTP connection pool)
    # is created once per provider, not once per request
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "anthropic":
        return AnthropicProvider()
    if provider_name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}")


def get_llm_provider() -> LLMProvider:
    return _build_provider(os.getenv("LLM_PROVIDER", "openai").lower())
