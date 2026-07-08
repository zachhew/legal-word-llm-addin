import asyncio
from pathlib import Path

from app.schemas.chat import LegalRequest
from app.schemas.context import LegalFact
from app.schemas.providers import ProviderSettings
from app.services.context.basic_signal_extractor import extract_basic_signals
from app.services.context.conflict_detector import detect_conflict_candidates
from app.services.context.context_builder import build_context
from app.services.context.document_chunker import build_document_chunks
from app.services.context.llm_fact_extractor import extract_legal_facts_with_llm
from app.services.prompt_builder import build_legal_messages


class FakeFactProvider:
    async def generate_json(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        return {
            "facts": [
                {
                    "fact_type": "jurisdiction",
                    "value": "Арбитражный суд города Москвы",
                    "normalized_value": "арбитражный суд города москвы",
                    "chunk_id": "chunk_0001",
                    "quote": "Споры рассматриваются в Арбитражном суде города Москвы.",
                    "confidence": 0.95,
                },
                {
                    "fact_type": "jurisdiction",
                    "value": "Арбитражный суд Санкт-Петербурга и Ленинградской области",
                    "normalized_value": (
                        "арбитражный суд санкт-петербурга и ленинградской области"
                    ),
                    "chunk_id": "chunk_0002",
                    "quote": (
                        "Подсудность определяется Арбитражным судом "
                        "Санкт-Петербурга и Ленинградской области."
                    ),
                    "confidence": 0.95,
                },
            ]
        }


def test_document_chunker_preserves_sections() -> None:
    text = """1. Предмет договора
Исполнитель оказывает услуги.

2. Порядок оплаты
Заказчик оплачивает услуги в течение 10 рабочих дней."""

    chunks = build_document_chunks(text)

    assert len(chunks) == 2
    assert chunks[0].title == "1. Предмет договора"
    assert chunks[1].title == "2. Порядок оплаты"
    assert chunks[1].section_path == ["2. Порядок оплаты"]


def test_basic_signal_extractor_extracts_periods() -> None:
    chunks = build_document_chunks(
        "2. Порядок оплаты\nЗаказчик оплачивает счет в течение 10 рабочих дней."
    )

    signals = extract_basic_signals(chunks)

    assert any(signal.signal_type == "period" for signal in signals)
    assert any(signal.value == "в течение 10 рабочих дней" for signal in signals)


def test_basic_signal_extractor_extracts_percentages() -> None:
    chunks = build_document_chunks("4. SLA\nДоступность сервиса составляет 99,9% в месяц.")

    signals = extract_basic_signals(chunks)

    assert any(signal.signal_type == "percentage" and signal.value == "99,9%" for signal in signals)


def test_basic_signal_extractor_does_not_classify_jurisdiction() -> None:
    chunks = build_document_chunks(
        """14. Разрешение споров
Споры рассматриваются в Арбитражном суде города Москвы."""
    )

    signals = extract_basic_signals(chunks)

    assert not any(signal.signal_type == "jurisdiction" for signal in signals)


def test_conflict_detector_groups_different_fact_values() -> None:
    facts = [
        LegalFact(
            fact_id="fact_0001",
            fact_type="jurisdiction",
            value="Арбитражный суд города Москвы",
            normalized_value="арбитражный суд города москвы",
            chunk_id="chunk_0001",
        ),
        LegalFact(
            fact_id="fact_0002",
            fact_type="jurisdiction",
            value="Арбитражный суд Санкт-Петербурга и Ленинградской области",
            normalized_value="арбитражный суд санкт-петербурга и ленинградской области",
            chunk_id="chunk_0002",
        ),
    ]

    conflicts = detect_conflict_candidates(facts)

    assert len(conflicts) == 1
    assert conflicts[0].fact_type == "jurisdiction"


def test_llm_fact_extractor_normalizes_structured_facts() -> None:
    chunks = build_document_chunks(
        """14. Разрешение споров
Споры рассматриваются в Арбитражном суде города Москвы.

15. Подсудность
Подсудность определяется Арбитражным судом Санкт-Петербурга и Ленинградской области."""
    )
    signals = extract_basic_signals(chunks)

    facts = asyncio.run(
        extract_legal_facts_with_llm(
            chunks=chunks,
            provider_settings=ProviderSettings(
                provider="openai_compatible",
                model="test-model",
                base_url="http://llm.test/v1",
                api_key="test-key",
            ),
            provider=FakeFactProvider(),
            scenario="inconsistency_check",
            raw_signals=signals,
        )
    )

    assert len(facts) == 2
    assert {fact.fact_type for fact in facts} == {"jurisdiction"}
    assert {fact.chunk_id for fact in facts} == {"chunk_0001", "chunk_0002"}


def test_context_builder_uses_llm_facts_for_inconsistency_conflicts() -> None:
    full_text = """14. Разрешение споров
Споры рассматриваются в Арбитражном суде города Москвы.

15. Подсудность
Подсудность определяется Арбитражным судом Санкт-Петербурга и Ленинградской области."""
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
        }
    )

    built_context = asyncio.run(
        build_context(
            request,
            provider_settings=ProviderSettings(
                provider="openai_compatible",
                model="test-model",
                base_url="http://llm.test/v1",
                api_key="test-key",
            ),
            provider=FakeFactProvider(),
        )
    )

    assert built_context.metadata.extraction_strategy == "llm_fact_extraction"
    assert built_context.metadata.facts_used == 2
    assert built_context.metadata.conflict_candidates_used == 1
    assert "CONFLICT CANDIDATES" in built_context.context_text
    assert "Арбитражный суд города Москвы" in built_context.context_text
    assert "Арбитражный суд Санкт-Петербурга" in built_context.context_text


def test_mock_inconsistency_still_returns_context_metadata() -> None:
    full_text = """4. Стоимость и оплата
Заказчик оплачивает счет в течение 10 рабочих дней.

5. SLA
Доступность сервиса составляет 99,9%."""
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
            "provider": {"provider": "mock"},
        }
    )

    built_context = asyncio.run(build_context(request))

    assert built_context.metadata.strategy == "fact_extraction_conflict_detection"
    assert built_context.metadata.extraction_strategy == "mock_fact_extraction"
    assert built_context.metadata.raw_signals_used > 0


def test_context_builder_does_not_use_legal_regex_patterns() -> None:
    source_dir = Path(__file__).resolve().parents[1] / "app" / "services" / "context"
    combined_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in source_dir.glob("*.py")
        if path.name != "retrieval_service.py"
    )

    assert "JURISDICTION_PATTERNS" not in combined_source
    assert "GOVERNING_LAW_PATTERNS" not in combined_source
    assert "LIABILITY_PATTERNS" not in combined_source
    assert "TERMINATION_PATTERNS" not in combined_source


def test_prompt_builder_mentions_extracted_facts() -> None:
    request = LegalRequest.model_validate(
        {
            "scenario": "inconsistency_check",
            "message": "Найди противоречия.",
            "document_context": {
                "mode": "full_document",
                "text": "Договор действует до 01.01.2027.",
                "character_count": 33,
            },
        }
    )

    messages = build_legal_messages(request)

    assert "Legal facts" in messages[0]["content"]
    assert "Raw signals" in messages[0]["content"]
