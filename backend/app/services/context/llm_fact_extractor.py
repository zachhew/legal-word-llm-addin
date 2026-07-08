import json
import re
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.providers.base import LLMProvider
from app.schemas.context import DocumentChunk, LegalFact, RawSignal
from app.schemas.providers import ProviderSettings

ALLOWED_FACT_TYPES = {
    "payment_period",
    "acceptance_period",
    "liability_cap",
    "penalty_amount",
    "sla_value",
    "incident_notice_period",
    "data_retention_period",
    "termination_notice_period",
    "jurisdiction",
    "governing_law",
    "contract_term",
    "party_name",
    "confidentiality_obligation",
    "ip_rights",
    "data_processing_obligation",
    "other",
}

FACT_EXTRACTION_SCHEMA = {
    "facts": [
        {
            "fact_type": "payment_period",
            "value": "10 рабочих дней",
            "normalized_value": "10 рабочих дней",
            "chunk_id": "chunk_0004",
            "quote": "Оплата производится в течение 10 рабочих дней.",
            "confidence": 0.9,
        }
    ]
}

SYSTEM_PROMPT = f"""You are a legal fact extraction engine.
Extract only facts explicitly present in the provided document chunks.
Do not provide legal advice.
Do not infer facts outside the text.
Use only these fact_type values:
{", ".join(sorted(ALLOWED_FACT_TYPES))}
Always include chunk_id.
Use a short quote from the source chunk when possible.
Return valid JSON only.

Expected JSON schema:
{json.dumps(FACT_EXTRACTION_SCHEMA, ensure_ascii=False, indent=2)}
"""

MAX_CHUNK_TEXT_CHARS = 1800


def _normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace(",", ".")).strip(" .;:,")


def _signals_for_chunk(raw_signals: list[RawSignal], chunk_id: str) -> list[dict[str, Any]]:
    return [
        {
            "signal_id": signal.signal_id,
            "signal_type": signal.signal_type,
            "value": signal.value,
            "start": signal.start,
            "end": signal.end,
        }
        for signal in raw_signals
        if signal.chunk_id == chunk_id
    ]


def build_fact_extraction_messages(
    *,
    chunks: list[DocumentChunk],
    scenario: str,
    raw_signals: list[RawSignal] | None = None,
) -> list[dict[str, str]]:
    raw_signals = raw_signals or []
    payload = {
        "scenario": scenario,
        "instruction": (
            "Extract semantic legal facts only. Raw signals are low-level hints, "
            "not classifications."
        ),
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "section_path": chunk.section_path,
                "text": chunk.text[:MAX_CHUNK_TEXT_CHARS],
                "raw_signals": _signals_for_chunk(raw_signals, chunk.chunk_id),
            }
            for chunk in chunks
        ],
    }

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]


def _fact_from_raw(raw_fact: Any, index: int) -> LegalFact | None:
    if not isinstance(raw_fact, dict):
        return None

    fact_type = str(raw_fact.get("fact_type", "other"))
    if fact_type not in ALLOWED_FACT_TYPES:
        fact_type = "other"

    value = str(raw_fact.get("value", "")).strip()
    chunk_id = str(raw_fact.get("chunk_id", "")).strip()
    if not value or not chunk_id:
        return None

    confidence = raw_fact.get("confidence", 1.0)
    try:
        confidence_float = float(confidence)
    except (TypeError, ValueError):
        confidence_float = 1.0

    payload = {
        "fact_id": f"fact_{index:04d}",
        "fact_type": fact_type,
        "value": value,
        "normalized_value": raw_fact.get("normalized_value") or _normalize_value(value),
        "chunk_id": chunk_id,
        "quote": raw_fact.get("quote"),
        "confidence": max(0.0, min(confidence_float, 1.0)),
    }

    try:
        return LegalFact.model_validate(payload)
    except ValidationError:
        return None


def normalize_llm_fact_response(raw_response: dict) -> list[LegalFact]:
    raw_facts = raw_response.get("facts", [])
    if not isinstance(raw_facts, list):
        return []

    facts: list[LegalFact] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_fact in raw_facts:
        fact = _fact_from_raw(raw_fact, len(facts) + 1)
        if fact is None:
            continue

        key = (
            fact.fact_type,
            fact.normalized_value or _normalize_value(fact.value),
            fact.chunk_id,
        )
        if key in seen:
            continue
        seen.add(key)
        facts.append(fact)

    return facts


async def extract_legal_facts_with_llm(
    chunks: list[DocumentChunk],
    provider_settings: ProviderSettings,
    provider: LLMProvider,
    scenario: str,
    raw_signals: list[RawSignal] | None = None,
) -> list[LegalFact]:
    base_url = provider_settings.base_url
    if provider_settings.provider == "openrouter" and not base_url:
        base_url = settings.openrouter_base_url

    messages = build_fact_extraction_messages(
        chunks=chunks,
        scenario=scenario,
        raw_signals=raw_signals,
    )
    raw_response = await provider.generate_json(
        messages=messages,
        api_key=provider_settings.api_key or "",
        model=provider_settings.model or "",
        base_url=base_url,
        temperature=0.0,
    )

    return normalize_llm_fact_response(raw_response)
