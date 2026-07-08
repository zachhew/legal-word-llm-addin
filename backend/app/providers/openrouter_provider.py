from typing import Any

from app.core.config import get_settings
from app.core.errors import InvalidLLMResponseError
from app.providers.openai_compatible_provider import OpenAICompatibleProvider

OPENROUTER_BASE_URL = get_settings().openrouter_base_url


class OpenRouterProvider(OpenAICompatibleProvider):
    provider_label = "OpenRouter"

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        settings = get_settings()
        resolved_base_url = base_url or settings.openrouter_base_url
        url = f"{resolved_base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_referer,
            "X-Title": settings.openrouter_title,
        }

        response = await self._post_chat_completions(
            url=url,
            headers=headers,
            payload=payload,
        )

        try:
            response_payload = response.json()
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise InvalidLLMResponseError(
                "OpenRouter response does not match chat completions format."
            ) from error

        return self._parse_content(content)
