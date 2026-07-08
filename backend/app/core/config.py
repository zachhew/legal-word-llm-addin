from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Legal Word LLM Assistant"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    cors_origins: str = (
        "https://localhost:3000,http://localhost:3000,"
        "https://127.0.0.1:3000,http://127.0.0.1:3000"
    )

    default_provider: str = "openrouter"
    default_model: str = "qwen/qwen3.5-flash-02-23"
    recommended_openrouter_model: str = "qwen/qwen3-235b-a22b-thinking-2507"

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_compatible_base_url: str = ""

    llm_request_timeout_seconds: int = 60
    llm_temperature: float = 0.2
    llm_json_repair_attempts: int = 1

    max_full_context_chars: int = 30000
    max_context_chars: int = 18000
    chunk_target_chars: int = 2500
    chunk_overlap_chars: int = 300
    top_k_chunks: int = 6

    max_document_text_chars: int = 200000
    max_selection_text_chars: int = 30000
    openrouter_referer: str = Field(
        default="http://localhost:3000",
        validation_alias="OPENROUTER_HTTP_REFERER",
    )
    openrouter_title: str = Field(
        default="Legal Word LLM Add-in",
        validation_alias="OPENROUTER_APP_TITLE",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    return settings
