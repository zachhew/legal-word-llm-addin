import json
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import InvalidLLMResponseError, LLMProviderError

MAX_PROVIDER_ERROR_LENGTH = 500
SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(api[_ -]?key\s*[:=]\s*)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(authorization\s*[:=]\s*)[A-Za-z0-9._\- ]+", re.IGNORECASE),
)


class OpenAICompatibleProvider:
    provider_label = "LLM provider"

    def _redact_match(self, match: re.Match[str]) -> str:
        if match.lastindex:
            return f"{match.group(1)}[redacted]"

        return "[redacted]"

    def _sanitize_provider_message(self, message: str) -> str:
        sanitized = message
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub(self._redact_match, sanitized)

        return sanitized[:MAX_PROVIDER_ERROR_LENGTH]

    def _provider_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            if not text:
                return ""

            return self._sanitize_provider_message(text)

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("detail")
                if message:
                    return self._sanitize_provider_message(str(message))

            for key in ("message", "detail", "error_description"):
                value = payload.get(key)
                if value:
                    return self._sanitize_provider_message(str(value))

        return ""

    def _content_to_text(self, content: object) -> str | None:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if not isinstance(item, dict):
                    continue

                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
                        break

            return "\n".join(parts) if parts else None

        if isinstance(content, dict):
            for key in ("text", "content"):
                value = content.get(key)
                if isinstance(value, str):
                    return value

        return None

    def _parse_content(self, content: object) -> dict:
        if isinstance(content, dict):
            return content

        cleaned_content = self._content_to_text(content)
        if cleaned_content is None:
            raise InvalidLLMResponseError(
                "LLM provider content could not be converted to JSON text."
            )

        cleaned_content = cleaned_content.strip()
        cleaned_content = re.sub(r"^```(?:json)?\s*", "", cleaned_content, flags=re.IGNORECASE)
        cleaned_content = re.sub(r"\s*```$", "", cleaned_content).strip()

        try:
            parsed = json.loads(cleaned_content)
        except json.JSONDecodeError as error:
            object_match = re.search(r"\{.*\}", cleaned_content, flags=re.DOTALL)
            if not object_match:
                raise InvalidLLMResponseError("LLM provider content is not valid JSON.") from error

            try:
                parsed = json.loads(object_match.group(0))
            except json.JSONDecodeError as nested_error:
                raise InvalidLLMResponseError(
                    "LLM provider content is not valid JSON."
                ) from nested_error

        if not isinstance(parsed, dict):
            raise InvalidLLMResponseError("LLM provider JSON response must be an object.")

        return parsed

    def _build_json_repair_messages(self, content: object) -> list[dict[str, str]]:
        content_text = self._content_to_text(content)
        if content_text is None:
            content_text = json.dumps(content, ensure_ascii=False)

        return [
            {
                "role": "system",
                "content": (
                    "You repair malformed LLM JSON responses. Return one valid JSON "
                    "object only. Do not add markdown, comments, explanations, or new "
                    "facts. Preserve the original keys and values whenever possible."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Repair this content into a valid JSON object:\n\n"
                    f"{content_text}"
                ),
            },
        ]

    def _should_retry_without_response_format(
        self, status_code: int, provider_message: str
    ) -> bool:
        message = provider_message.lower()
        return status_code == 400 and (
            "response_format" in message
            or "json_object" in message
            or "json mode" in message
            or "not support" in message
        )

    async def _post_chat_completions(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            provider_message = self._provider_error_message(error.response)
            if (
                "response_format" in payload
                and self._should_retry_without_response_format(status_code, provider_message)
            ):
                retry_payload = dict(payload)
                retry_payload.pop("response_format", None)
                try:
                    async with httpx.AsyncClient(
                        timeout=settings.llm_request_timeout_seconds
                    ) as client:
                        response = await client.post(url, headers=headers, json=retry_payload)
                        response.raise_for_status()
                        return response
                except httpx.HTTPStatusError as retry_error:
                    status_code = retry_error.response.status_code
                    provider_message = self._provider_error_message(retry_error.response)
                    error = retry_error

            message = f"{self.provider_label} returned HTTP {status_code}."
            if provider_message:
                message = f"{message} Provider message: {provider_message}"

            raise LLMProviderError(message) from error
        except httpx.HTTPError as error:
            raise LLMProviderError("LLM provider request failed.") from error

    async def _request_json_repair(
        self,
        *,
        url: str,
        headers: dict[str, str],
        model: str,
        content: object,
        temperature: float,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._build_json_repair_messages(content),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        response = await self._post_chat_completions(
            url=url,
            headers=headers,
            payload=payload,
        )

        try:
            response_payload = response.json()
            repaired_content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise InvalidLLMResponseError(
                "LLM JSON repair response does not match chat completions format."
            ) from error

        return self._parse_content(repaired_content)

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        if not base_url:
            raise LLMProviderError("OpenAI-compatible base URL is required.")

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        response = await self._post_chat_completions(
            url=url,
            headers=headers,
            payload=payload,
        )

        try:
            response_payload = response.json()
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise InvalidLLMResponseError(
                "LLM provider response does not match chat completions format."
            ) from error

        try:
            return self._parse_content(content)
        except InvalidLLMResponseError as parse_error:
            settings = get_settings()
            if settings.llm_json_repair_attempts <= 0:
                raise parse_error

            try:
                return await self._request_json_repair(
                    url=url,
                    headers=headers,
                    model=model,
                    content=content,
                    temperature=0.0,
                )
            except LLMProviderError as repair_error:
                raise InvalidLLMResponseError(
                    "LLM provider content could not be repaired into valid JSON."
                ) from repair_error
