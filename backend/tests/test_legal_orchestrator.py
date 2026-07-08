import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.schemas.chat import LegalRequest
from app.services.prompt_builder import build_legal_messages


class FakeProvider:
    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        return {
            "answer": "LLM-анализ выполнен.",
            "suggested_actions": [
                {
                    "type": "replace_selection",
                    "title": "Переписать пункт",
                    "original_text": "Стороны согласуют условия позже.",
                    "proposed_text": (
                        "Стороны обязуются согласовать существенные условия в письменной "
                        "форме до начала исполнения обязательств."
                    ),
                    "rationale": "Правка снижает неопределенность условия.",
                }
            ],
            "warnings": [],
        }


class FakeAnswerOnlyRewriteProvider:
    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        return {
            "answer": (
                "Предлагаемая редакция: Стороны обязуются согласовать существенные "
                "условия в письменной форме до начала оказания услуг.\n\n"
                "Обоснование: Правка убирает неопределенность срока согласования "
                "и фиксирует письменную форму договоренности."
            ),
            "suggested_actions": [],
            "warnings": [],
        }


class FakeAnswerOnlyRewriteWithoutRationaleProvider:
    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        return {
            "answer": (
                "Предлагаемая редакция: Стороны обязуются согласовать существенные "
                "условия в письменной форме до начала оказания услуг."
            ),
            "suggested_actions": [],
            "warnings": [],
        }


class FakeDuplicateInconsistencyProvider:
    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        if "legal fact extraction engine" in messages[0]["content"]:
            return {
                "facts": [
                    {
                        "fact_type": "payment_period",
                        "value": "10 рабочих дней",
                        "normalized_value": "10 рабочих дней",
                        "chunk_id": "chunk_0001",
                        "quote": "Заказчик оплачивает счет в течение 10 рабочих дней.",
                        "confidence": 0.9,
                    },
                    {
                        "fact_type": "payment_period",
                        "value": "15 календарных дней",
                        "normalized_value": "15 календарных дней",
                        "chunk_id": "chunk_0002",
                        "quote": (
                            "Оплата производится в течение 15 календарных дней после "
                            "подписания акта."
                        ),
                        "confidence": 0.9,
                    },
                ]
            }

        return {
            "answer": "LLM нашел похожие противоречия.",
            "findings": [
                {
                    "type": "inconsistency",
                    "title": "Сроки оплаты",
                    "severity": "high",
                    "explanation": "В документе указаны разные сроки оплаты.",
                    "evidence_chunk_ids": ["chunk_0001", "chunk_0002"],
                    "recommendation": "Уточнить срок оплаты.",
                }
            ],
            "suggested_actions": [],
            "warnings": [],
        }


def test_mock_provider_still_works() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "chat",
            "message": "Проверь документ.",
            "document_context": {
                "mode": "selection",
                "text": "Текст договора.",
                "character_count": 14,
            },
            "provider": {"provider": "mock", "model": "mock-legal-model"},
        },
    )

    assert response.status_code == 200
    assert response.json()["scenario"] == "chat"


def test_provider_settings_validation_requires_api_key_for_openrouter() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "risk_review",
            "message": "Проверь риски.",
            "document_context": {
                "mode": "selection",
                "text": "Ответственность не ограничена.",
                "character_count": 29,
            },
            "provider": {"provider": "openrouter", "model": "qwen/qwen3.5-flash-02-23"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "MISSING_PROVIDER_SETTINGS"


def test_provider_settings_validation_requires_model_for_openrouter() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "risk_review",
            "message": "Проверь риски.",
            "document_context": {
                "mode": "selection",
                "text": "Ответственность не ограничена.",
                "character_count": 29,
            },
            "provider": {"provider": "openrouter", "api_key": "test-key"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "MISSING_PROVIDER_SETTINGS"


def test_provider_settings_validation_requires_base_url_for_openai_compatible() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "risk_review",
            "message": "Проверь риски.",
            "document_context": {
                "mode": "selection",
                "text": "Ответственность не ограничена.",
                "character_count": 29,
            },
            "provider": {
                "provider": "openai_compatible",
                "model": "local-model",
                "api_key": "test-key",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "MISSING_PROVIDER_SETTINGS"


def test_prompt_builder_contains_document_context() -> None:
    request = LegalRequest.model_validate(
        {
            "scenario": "inconsistency_check",
            "message": "Найди противоречия.",
            "document_context": {
                "mode": "full_document",
                "text": "Договор действует до 01.01.2027. Договор действует бессрочно.",
                "character_count": 63,
            },
        }
    )

    messages = build_legal_messages(request)

    assert messages[0]["role"] == "system"
    assert "strictly" not in messages[0]["content"].lower()
    assert "Договор действует до 01.01.2027" in messages[1]["content"]
    assert "inconsistency_check" in messages[1]["content"]


def test_llm_action_original_text_matches_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import legal_orchestrator

    monkeypatch.setattr(legal_orchestrator, "get_llm_provider", lambda _name: FakeProvider())
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "clause_rewrite",
            "message": "Перепиши пункт.",
            "document_context": {
                "mode": "selection",
                "text": "Стороны согласуют условия позже.",
                "character_count": 33,
            },
            "provider": {
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "http://llm.test/v1",
                "api_key": "test-key",
            },
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["suggested_actions"]
    assert payload["suggested_actions"][0]["original_text"] == "Стороны согласуют условия позже."


def test_clause_rewrite_answer_only_becomes_suggested_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import legal_orchestrator

    monkeypatch.setattr(
        legal_orchestrator,
        "get_llm_provider",
        lambda _name: FakeAnswerOnlyRewriteProvider(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "clause_rewrite",
            "message": "Перепиши пункт.",
            "document_context": {
                "mode": "selection",
                "text": "Стороны согласуют условия позже.",
                "character_count": 33,
            },
            "provider": {
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "http://llm.test/v1",
                "api_key": "test-key",
            },
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["suggested_actions"]
    assert payload["suggested_actions"][0]["original_text"] == (
        "Стороны согласуют условия позже."
    )
    assert payload["suggested_actions"][0]["proposed_text"] == (
        "Стороны обязуются согласовать существенные условия в письменной форме "
        "до начала оказания услуг."
    )
    assert payload["suggested_actions"][0]["rationale"] == (
        "Правка убирает неопределенность срока согласования и фиксирует письменную "
        "форму договоренности."
    )
    assert payload["suggested_actions"][0]["rationale_source"] == "llm"


def test_clause_rewrite_answer_only_without_rationale_hides_fallback_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import legal_orchestrator

    monkeypatch.setattr(
        legal_orchestrator,
        "get_llm_provider",
        lambda _name: FakeAnswerOnlyRewriteWithoutRationaleProvider(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "clause_rewrite",
            "message": "Перепиши пункт.",
            "document_context": {
                "mode": "selection",
                "text": "Стороны согласуют условия позже.",
                "character_count": 33,
            },
            "provider": {
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "http://llm.test/v1",
                "api_key": "test-key",
            },
        },
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["suggested_actions"]
    assert payload["suggested_actions"][0]["rationale"] == ""
    assert payload["suggested_actions"][0]["rationale_source"] == "fallback"


def test_inconsistency_check_returns_llm_top_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import legal_orchestrator

    monkeypatch.setattr(
        legal_orchestrator,
        "get_llm_provider",
        lambda _name: FakeDuplicateInconsistencyProvider(),
    )
    full_text = """2. Порядок оплаты
Заказчик оплачивает счет в течение 10 рабочих дней.

8. Заключительные положения
Оплата производится в течение 15 календарных дней после подписания акта."""
    request = LegalRequest.model_validate(
        {
            "scenario": "inconsistency_check",
            "message": "Найди противоречия.",
            "document_context": {
                "mode": "auto",
                "text": full_text,
                "full_text": full_text,
                "character_count": len(full_text),
            },
            "provider": {
                "provider": "openai_compatible",
                "model": "test-model",
                "base_url": "http://llm.test/v1",
                "api_key": "test-key",
            },
        }
    )

    response = asyncio.run(legal_orchestrator.run_legal_scenario(request))

    assert response.context_metadata is not None
    assert response.context_metadata.conflict_candidates_used == 1
    assert len(response.findings) == 1
    assert response.findings[0].title == "Сроки оплаты"


def test_run_endpoint_requires_job_for_full_document_inconsistency() -> None:
    client = TestClient(app)
    full_text = """2. Порядок оплаты
Заказчик оплачивает счет в течение 10 рабочих дней.

8. Заключительные положения
Оплата производится в течение 15 календарных дней после подписания акта."""

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "inconsistency_check",
            "message": "Найди противоречия.",
            "document_context": {
                "mode": "auto",
                "text": full_text,
                "full_text": full_text,
                "character_count": len(full_text),
            },
            "provider": {"provider": "mock"},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "USE_JOB_ENDPOINT"


def test_provider_error_message_is_sanitized() -> None:
    provider = OpenAICompatibleProvider()
    request = httpx.Request("POST", "https://provider.test/chat/completions")
    response = httpx.Response(
        401,
        request=request,
        json={"error": {"message": "Invalid Authorization: Bearer secret-token-123456"}},
    )

    message = provider._provider_error_message(response)

    assert "[redacted]" in message
    assert "secret-token" not in message


def test_oversized_document_request_returns_413() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/legal/run",
        json={
            "scenario": "chat",
            "message": "Проверь документ.",
            "document_context": {
                "mode": "full_document",
                "text": "а" * 200_001,
                "character_count": 200_001,
            },
            "provider": {"provider": "mock"},
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "REQUEST_TOO_LARGE"
