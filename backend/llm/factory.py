import os
from llm.openai_provider import OpenAIProvider
from llm.anthropic_provider import AnthropicProvider
from llm.gemini_provider import GeminiProvider


def get_llm_provider():
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "anthropic":
        return AnthropicProvider()
    elif provider_name == "gemini":
        return GeminiProvider()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}")
