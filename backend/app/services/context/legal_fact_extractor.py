import re

from app.schemas.context import DocumentChunk, LegalFact, RawSignal
from app.services.context.basic_signal_extractor import extract_basic_signals
from app.services.context.conflict_detector import detect_conflict_candidates

__all__ = [
    "detect_conflict_candidates",
    "extract_legal_facts",
    "extract_mock_legal_facts",
]


def _normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace(",", ".")).strip(" .;:,")


def _title_contains(chunk: DocumentChunk, *needles: str) -> bool:
    title = " ".join([chunk.title or "", *chunk.section_path]).lower()
    return any(needle.lower() in title for needle in needles)


def _mock_fact_type_for_signal(chunk: DocumentChunk, signal: RawSignal) -> str:
    if signal.signal_type == "percentage" and _title_contains(chunk, "sla", "сервис"):
        return "sla_value"
    if signal.signal_type == "percentage":
        return "penalty_amount"
    if signal.signal_type == "period" and _title_contains(chunk, "оплат"):
        return "payment_period"
    if signal.signal_type == "period" and _title_contains(chunk, "прием", "приём", "акт"):
        return "acceptance_period"
    if signal.signal_type == "period" and _title_contains(chunk, "инцидент", "сервис", "sla"):
        return "incident_notice_period"
    if signal.signal_type == "period" and _title_contains(chunk, "данн", "экспорт"):
        return "data_retention_period"
    if signal.signal_type == "period" and _title_contains(chunk, "растор", "прекращ"):
        return "termination_notice_period"
    if signal.signal_type == "period" and _title_contains(chunk, "срок", "договор"):
        return "contract_term"
    return "other"


def extract_mock_legal_facts(
    chunks: list[DocumentChunk],
    raw_signals: list[RawSignal] | None = None,
) -> list[LegalFact]:
    raw_signals = raw_signals or extract_basic_signals(chunks)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    facts: list[LegalFact] = []
    seen: set[tuple[str, str, str]] = set()

    for signal in raw_signals:
        chunk = chunks_by_id.get(signal.chunk_id)
        if chunk is None:
            continue

        fact_type = _mock_fact_type_for_signal(chunk, signal)
        if fact_type == "other":
            continue

        normalized = _normalize_value(signal.value)
        key = (fact_type, normalized, signal.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            LegalFact(
                fact_id=f"fact_{len(facts) + 1:04d}",
                fact_type=fact_type,
                value=signal.value,
                normalized_value=normalized,
                chunk_id=signal.chunk_id,
                quote=None,
                confidence=0.55,
            )
        )

    return facts


def extract_legal_facts(chunks: list[DocumentChunk]) -> list[LegalFact]:
    return extract_mock_legal_facts(chunks)
