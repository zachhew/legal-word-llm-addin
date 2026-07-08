import re
from collections import defaultdict

from app.schemas.context import ConflictCandidate, LegalFact

CONFLICT_FACT_TYPES = {
    "payment_period",
    "acceptance_period",
    "liability_cap",
    "sla_value",
    "incident_notice_period",
    "data_retention_period",
    "termination_notice_period",
    "jurisdiction",
    "governing_law",
    "contract_term",
}


def _normalized_fact_value(fact: LegalFact) -> str:
    value = fact.normalized_value or fact.value
    return re.sub(r"\s+", " ", value.lower().replace(",", ".")).strip(" .;:,")


def detect_conflict_candidates(facts: list[LegalFact]) -> list[ConflictCandidate]:
    grouped: dict[str, list[LegalFact]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type in CONFLICT_FACT_TYPES:
            grouped[fact.fact_type].append(fact)

    conflicts: list[ConflictCandidate] = []
    for fact_type, fact_group in grouped.items():
        values = {_normalized_fact_value(fact) for fact in fact_group}
        chunks = {fact.chunk_id for fact in fact_group}
        if len(values) < 2 or len(chunks) < 2:
            continue

        conflicts.append(
            ConflictCandidate(
                conflict_id=f"conflict_{len(conflicts) + 1:04d}",
                fact_type=fact_type,
                facts=fact_group,
                reason="Multiple different values were extracted for the same legal fact type.",
            )
        )

    return conflicts
