from typing import Literal

from pydantic import BaseModel

ProviderName = Literal["mock", "openrouter", "openai_compatible"]


class ProviderSettings(BaseModel):
    provider: ProviderName = "mock"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
