from app.providers.base import LLMProvider
from app.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.providers.openrouter_provider import OpenRouterProvider


def get_llm_provider(provider_name: str) -> LLMProvider | None:
    if provider_name == "mock":
        return None

    if provider_name == "openrouter":
        return OpenRouterProvider()

    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider()

    raise ValueError(f"Unsupported provider: {provider_name}")
