from app.core.config import Settings, settings
from app.services.context import context_builder, document_chunker


def test_settings_defaults() -> None:
    default_settings = Settings(_env_file=None)

    assert default_settings.app_env == "development"
    assert default_settings.app_name == "Legal Word LLM Assistant"
    assert default_settings.default_provider == "openrouter"
    assert default_settings.default_model == "qwen/qwen3.5-flash-02-23"
    assert default_settings.recommended_openrouter_model == "qwen/qwen3-235b-a22b-thinking-2507"
    assert default_settings.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_settings_cors_origin_list() -> None:
    default_settings = Settings(_env_file=None)

    assert "https://localhost:3000" in default_settings.cors_origin_list
    assert "http://127.0.0.1:3000" in default_settings.cors_origin_list
    assert all(origin.strip() == origin for origin in default_settings.cors_origin_list)


def test_settings_does_not_define_api_keys() -> None:
    default_settings = Settings(_env_file=None)

    assert not hasattr(default_settings, "openrouter_api_key")
    assert not hasattr(default_settings, "openai_api_key")
    assert not hasattr(default_settings, "api_key")


def test_context_limits_loaded_from_settings() -> None:
    assert context_builder.MAX_FULL_CONTEXT_CHARS == settings.max_full_context_chars
    assert context_builder.MAX_CONTEXT_CHARS == settings.max_context_chars
    assert context_builder.TOP_K_CHUNKS == settings.top_k_chunks
    assert document_chunker.CHUNK_TARGET_CHARS == settings.chunk_target_chars
    assert document_chunker.CHUNK_OVERLAP_CHARS == settings.chunk_overlap_chars
