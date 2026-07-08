from app.core.config import settings
from app.core.errors import InvalidLLMResponseError, LLMProviderError
from app.providers.base import LLMProvider
from app.schemas.chat import LegalRequest, LegalScenario
from app.schemas.context import (
    BuiltContext,
    ConflictCandidate,
    ContextMetadata,
    ContextSourceChunk,
    DocumentChunk,
    LegalFact,
    RawSignal,
)
from app.schemas.document import DocumentContextMode
from app.schemas.providers import ProviderSettings
from app.services.context.basic_signal_extractor import extract_basic_signals
from app.services.context.conflict_detector import detect_conflict_candidates
from app.services.context.document_chunker import build_document_chunks
from app.services.context.document_normalizer import normalize_document_text
from app.services.context.legal_fact_extractor import extract_mock_legal_facts
from app.services.context.llm_fact_extractor import extract_legal_facts_with_llm
from app.services.context.retrieval_service import retrieve_relevant_chunks

MAX_FULL_CONTEXT_CHARS = settings.max_full_context_chars
MAX_CONTEXT_CHARS = settings.max_context_chars
TOP_K_CHUNKS = settings.top_k_chunks
MAX_LLM_EXTRACTION_CHUNKS = 10
CONFLICT_EXCERPT_CHARS = 700


def _unique_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    result: list[DocumentChunk] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        result.append(chunk)
    return result


def _facts_for_chunks(facts: list[LegalFact], chunks: list[DocumentChunk]) -> list[LegalFact]:
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    return [fact for fact in facts if fact.chunk_id in chunk_ids]


def _signals_for_chunks(
    raw_signals: list[RawSignal],
    chunks: list[DocumentChunk],
) -> list[RawSignal]:
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    return [signal for signal in raw_signals if signal.chunk_id in chunk_ids]


def _select_chunks_for_llm_extraction(
    *,
    chunks: list[DocumentChunk],
    raw_signals: list[RawSignal],
    request: LegalRequest,
    limit: int = MAX_LLM_EXTRACTION_CHUNKS,
) -> list[DocumentChunk]:
    if len(chunks) <= limit:
        return chunks

    signal_counts: dict[str, int] = {}
    for signal in raw_signals:
        signal_counts[signal.chunk_id] = signal_counts.get(signal.chunk_id, 0) + 1

    signal_rich_chunks = sorted(
        chunks,
        key=lambda chunk: (
            signal_counts.get(chunk.chunk_id, 0),
            chunk.character_count,
        ),
        reverse=True,
    )[:limit]
    retrieved_chunks = retrieve_relevant_chunks(
        chunks,
        scenario=request.scenario,
        query=request.message,
        selected_party=request.selected_party,
        limit=limit,
    )

    return _unique_chunks([*signal_rich_chunks, *retrieved_chunks])[:limit]


def _compact_chunks_for_conflicts(
    chunks: list[DocumentChunk],
    conflict_candidates: list[ConflictCandidate],
) -> list[DocumentChunk]:
    conflict_values_by_chunk: dict[str, list[str]] = {}
    for conflict in conflict_candidates:
        for fact in conflict.facts:
            conflict_values_by_chunk.setdefault(fact.chunk_id, []).append(fact.value)

    compact_chunks: list[DocumentChunk] = []
    for chunk in chunks:
        values = conflict_values_by_chunk.get(chunk.chunk_id, [])
        if not values or len(chunk.text) <= CONFLICT_EXCERPT_CHARS:
            compact_chunks.append(chunk)
            continue

        match_positions = [
            chunk.text.lower().find(value.lower())
            for value in values
            if value and chunk.text.lower().find(value.lower()) >= 0
        ]
        center = min(match_positions) if match_positions else 0
        start = max(0, center - CONFLICT_EXCERPT_CHARS // 3)
        end = min(len(chunk.text), start + CONFLICT_EXCERPT_CHARS)
        excerpt = chunk.text[start:end].strip()
        if start > 0:
            excerpt = "... " + excerpt
        if end < len(chunk.text):
            excerpt = excerpt + " ..."

        compact_chunks.append(
            chunk.model_copy(
                update={
                    "text": excerpt,
                    "character_count": len(excerpt),
                }
            )
        )

    return compact_chunks


def _format_context_text(
    *,
    strategy: str,
    primary_selection: str | None,
    chunks: list[DocumentChunk],
    raw_signals: list[RawSignal],
    facts: list[LegalFact],
    conflict_candidates: list[ConflictCandidate],
) -> str:
    parts = [f"CONTEXT STRATEGY:\n{strategy}"]
    chunk_titles = {
        chunk.chunk_id: chunk.title or "Untitled"
        for chunk in chunks
    }

    if primary_selection:
        parts.append(f"PRIMARY SELECTION:\n{primary_selection.strip()}")

    if conflict_candidates:
        conflict_blocks = []
        for conflict in conflict_candidates:
            values = []
            seen_values = set()
            for fact in conflict.facts:
                if fact.value in seen_values:
                    continue
                seen_values.add(fact.value)
                values.append(f"{fact.value} ({fact.chunk_id})")
            fact_lines = [
                f"- {fact.fact_id}: {fact.value}, {fact.chunk_id} | "
                f"{chunk_titles.get(fact.chunk_id, 'Untitled')}"
                for fact in conflict.facts
            ]
            conflict_blocks.append(
                f"[{conflict.conflict_id} | {conflict.fact_type}]\n"
                + f"Values: {'; '.join(values)}\n"
                + "\n".join(fact_lines)
                + f"\nReason: {conflict.reason}"
            )
        parts.append("CONFLICT CANDIDATES:\n" + "\n\n".join(conflict_blocks))

    if raw_signals:
        signal_lines = [
            f"[{signal.signal_id} | {signal.signal_type} | {signal.chunk_id}] "
            f"{signal.value}"
            for signal in raw_signals
        ]
        parts.append("RAW SIGNALS:\n" + "\n".join(signal_lines))

    if facts:
        fact_lines = [
            f"[{fact.fact_id} | {fact.fact_type} | {fact.chunk_id}] {fact.value}"
            + (f"\nQuote: {fact.quote}" if fact.quote else "")
            for fact in facts
        ]
        parts.append("EXTRACTED LEGAL FACTS:\n" + "\n".join(fact_lines))

    if chunks:
        chunk_lines = []
        for chunk in chunks:
            title = chunk.title or "Untitled"
            chunk_lines.append(f"[{chunk.chunk_id} | {title}]\n{chunk.text}")
        parts.append("DOCUMENT CHUNKS:\n" + "\n\n".join(chunk_lines))

    return "\n\n".join(parts).strip()


def _finalize(
    *,
    strategy: str,
    context_text: str,
    chunks: list[DocumentChunk],
    raw_signals: list[RawSignal] | None = None,
    facts: list[LegalFact],
    conflict_candidates: list[ConflictCandidate] | None = None,
    source_document_characters: int,
    extraction_strategy: str | None = None,
    warnings: list[str] | None = None,
) -> BuiltContext:
    warnings = list(warnings or [])
    conflict_candidates = conflict_candidates or []
    raw_signals = raw_signals or []

    if len(context_text) > MAX_CONTEXT_CHARS:
        context_text = context_text[:MAX_CONTEXT_CHARS].rsplit("\n", 1)[0]
        warnings.append("Built context was truncated to fit the context character limit.")

    metadata = ContextMetadata(
        strategy=strategy,
        chunks_used=len(chunks),
        raw_signals_used=len(raw_signals),
        facts_used=len(facts),
        conflict_candidates_used=len(conflict_candidates),
        extraction_strategy=extraction_strategy,
        total_context_characters=len(context_text),
        source_document_characters=source_document_characters,
        source_chunks=[
            ContextSourceChunk(
                chunk_id=chunk.chunk_id,
                title=chunk.title,
                section_path=chunk.section_path,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
            )
            for chunk in chunks
        ],
        warnings=warnings,
    )

    return BuiltContext(
        strategy=strategy,
        context_text=context_text,
        chunks=chunks,
        raw_signals=raw_signals,
        facts=facts,
        conflict_candidates=conflict_candidates,
        metadata=metadata,
        warnings=warnings,
    )


def _empty_context(strategy: str, warning: str) -> BuiltContext:
    context_text = f"CONTEXT STRATEGY:\n{strategy}\n\nWARNINGS:\n{warning}"
    return _finalize(
        strategy=strategy,
        context_text=context_text,
        chunks=[],
        raw_signals=[],
        facts=[],
        source_document_characters=0,
        extraction_strategy="basic_signals_only",
        warnings=[warning],
    )


def _selection_chunk(selection_text: str) -> DocumentChunk:
    normalized = normalize_document_text(selection_text)
    return DocumentChunk(
        chunk_id="selection_0001",
        title="Selected clause",
        text=normalized,
        section_path=["Selected clause"],
        start_char=0,
        end_char=len(normalized),
        character_count=len(normalized),
    )


async def _extract_facts_for_context(
    *,
    chunks: list[DocumentChunk],
    request: LegalRequest,
    provider_settings: ProviderSettings | None,
    provider: LLMProvider | None,
    raw_signals: list[RawSignal],
) -> tuple[list[LegalFact], str, list[str]]:
    if provider_settings and provider_settings.provider != "mock" and provider is not None:
        try:
            facts = await extract_legal_facts_with_llm(
                chunks=chunks,
                provider_settings=provider_settings,
                provider=provider,
                scenario=request.scenario,
                raw_signals=raw_signals,
            )
            return facts, "llm_fact_extraction", []
        except (InvalidLLMResponseError, LLMProviderError) as error:
            facts = extract_mock_legal_facts(chunks, raw_signals)
            return facts, "llm_fact_extraction_fallback", [
                "LLM fact extraction failed; basic/mock context fallback was used. "
                f"Details: {error}"
            ]

    return extract_mock_legal_facts(chunks, raw_signals), "mock_fact_extraction", []


async def build_context(
    request: LegalRequest,
    provider_settings: ProviderSettings | None = None,
    provider: LLMProvider | None = None,
) -> BuiltContext:
    context = request.document_context
    primary_text = normalize_document_text(context.text or "")
    selection_text = normalize_document_text(
        context.selection_text
        or (primary_text if context.mode == DocumentContextMode.SELECTION else "")
    )
    full_text = normalize_document_text(context.full_text or primary_text)
    source_chars = len(full_text)

    if request.scenario == LegalScenario.CLAUSE_REWRITE:
        if not selection_text:
            return _empty_context("selection_required", "Clause rewrite requires selected text.")

        selected_chunk = _selection_chunk(selection_text)
        chunks = [selected_chunk]
        if full_text and full_text != selection_text:
            related = retrieve_relevant_chunks(
                build_document_chunks(full_text),
                scenario=request.scenario,
                query=request.message,
                selected_text=selection_text,
                selected_party=request.selected_party,
                limit=2,
            )
            chunks = _unique_chunks(chunks + related)
        raw_signals = extract_basic_signals(chunks)
        facts: list[LegalFact] = []
        text = _format_context_text(
            strategy="selection_required",
            primary_selection=selection_text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=[],
        )
        return _finalize(
            strategy="selection_required",
            context_text=text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            source_document_characters=source_chars or len(selection_text),
            extraction_strategy="basic_signals_only",
        )

    if request.scenario == LegalScenario.RISK_REVIEW:
        if selection_text:
            base_chunks = build_document_chunks(full_text) if full_text else []
            related = retrieve_relevant_chunks(
                base_chunks,
                scenario=request.scenario,
                query=request.message,
                selected_text=selection_text,
                selected_party=request.selected_party,
                limit=TOP_K_CHUNKS,
            )
            chunks = _unique_chunks([_selection_chunk(selection_text)] + related)
            raw_signals = extract_basic_signals(chunks)
            facts, extraction_strategy, extraction_warnings = await _extract_facts_for_context(
                chunks=chunks,
                request=request,
                provider_settings=provider_settings,
                provider=provider,
                raw_signals=raw_signals,
            )
            text = _format_context_text(
                strategy="selection_plus_related_legal_chunks",
                primary_selection=selection_text,
                chunks=chunks,
                raw_signals=raw_signals,
                facts=facts,
                conflict_candidates=[],
            )
            return _finalize(
                strategy="selection_plus_related_legal_chunks",
                context_text=text,
                chunks=chunks,
                raw_signals=raw_signals,
                facts=facts,
                source_document_characters=source_chars or len(selection_text),
                extraction_strategy=extraction_strategy,
                warnings=extraction_warnings,
            )

        chunks = retrieve_relevant_chunks(
            build_document_chunks(full_text),
            scenario=request.scenario,
            query=request.message,
            selected_party=request.selected_party,
            limit=TOP_K_CHUNKS,
        )
        raw_signals = extract_basic_signals(chunks)
        facts, extraction_strategy, extraction_warnings = await _extract_facts_for_context(
            chunks=chunks,
            request=request,
            provider_settings=provider_settings,
            provider=provider,
            raw_signals=raw_signals,
        )
        text = _format_context_text(
            strategy="smart_risk_retrieval",
            primary_selection=None,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=[],
        )
        return _finalize(
            strategy="smart_risk_retrieval",
            context_text=text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            source_document_characters=source_chars,
            extraction_strategy=extraction_strategy,
            warnings=extraction_warnings,
        )

    if request.scenario == LegalScenario.INCONSISTENCY_CHECK:
        if not full_text:
            return _empty_context(
                "fact_extraction_conflict_detection",
                "Inconsistency check requires full document text.",
            )

        all_chunks = build_document_chunks(full_text)
        all_raw_signals = extract_basic_signals(all_chunks)
        extraction_chunks = _select_chunks_for_llm_extraction(
            chunks=all_chunks,
            raw_signals=all_raw_signals,
            request=request,
        )
        extraction_raw_signals = _signals_for_chunks(all_raw_signals, extraction_chunks)
        all_facts, extraction_strategy, extraction_warnings = await _extract_facts_for_context(
            chunks=extraction_chunks,
            request=request,
            provider_settings=provider_settings,
            provider=provider,
            raw_signals=extraction_raw_signals,
        )
        if len(extraction_chunks) < len(all_chunks):
            extraction_warnings.append(
                "LLM fact extraction used selected signal-rich chunks to keep the "
                "full-document request responsive."
            )
        conflicts = detect_conflict_candidates(all_facts)
        conflict_chunk_ids = {
            fact.chunk_id for conflict in conflicts for fact in conflict.facts
        }
        conflict_chunks = [chunk for chunk in all_chunks if chunk.chunk_id in conflict_chunk_ids]
        if len(conflict_chunks) < TOP_K_CHUNKS:
            retrieved = retrieve_relevant_chunks(
                all_chunks,
                scenario=request.scenario,
                query=request.message,
                selected_party=request.selected_party,
                limit=TOP_K_CHUNKS,
            )
            conflict_chunks = _unique_chunks(conflict_chunks + retrieved)[:TOP_K_CHUNKS]

        compact_conflict_chunks = _compact_chunks_for_conflicts(conflict_chunks, conflicts)
        facts = _facts_for_chunks(all_facts, conflict_chunks)
        raw_signals = _signals_for_chunks(all_raw_signals, conflict_chunks)
        text = _format_context_text(
            strategy="fact_extraction_conflict_detection",
            primary_selection=None,
            chunks=compact_conflict_chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=conflicts,
        )
        return _finalize(
            strategy="fact_extraction_conflict_detection",
            context_text=text,
            chunks=compact_conflict_chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=conflicts,
            source_document_characters=source_chars,
            extraction_strategy=extraction_strategy,
            warnings=extraction_warnings,
        )

    if context.mode == DocumentContextMode.SELECTION and selection_text:
        chunk = _selection_chunk(selection_text)
        chunks = [chunk]
        raw_signals = extract_basic_signals(chunks)
        facts: list[LegalFact] = []
        text = _format_context_text(
            strategy="selection",
            primary_selection=selection_text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=[],
        )
        return _finalize(
            strategy="selection",
            context_text=text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            source_document_characters=source_chars or len(selection_text),
            extraction_strategy="basic_signals_only",
        )

    if (
        context.mode == DocumentContextMode.FULL_DOCUMENT
        and len(full_text) <= MAX_FULL_CONTEXT_CHARS
    ):
        chunks = build_document_chunks(full_text)
        raw_signals = extract_basic_signals(chunks)
        facts, extraction_strategy, extraction_warnings = await _extract_facts_for_context(
            chunks=chunks,
            request=request,
            provider_settings=provider_settings,
            provider=provider,
            raw_signals=raw_signals,
        )
        text = _format_context_text(
            strategy="full_document_within_limit",
            primary_selection=None,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            conflict_candidates=[],
        )
        return _finalize(
            strategy="full_document_within_limit",
            context_text=text,
            chunks=chunks,
            raw_signals=raw_signals,
            facts=facts,
            source_document_characters=source_chars,
            extraction_strategy=extraction_strategy,
            warnings=extraction_warnings,
        )

    warnings = []
    if (
        context.mode == DocumentContextMode.FULL_DOCUMENT
        and len(full_text) > MAX_FULL_CONTEXT_CHARS
    ):
        warnings.append(
            "Full document exceeded the direct context limit; smart retrieval was used."
        )

    chunks = retrieve_relevant_chunks(
        build_document_chunks(full_text),
        scenario=request.scenario,
        query=request.message,
        selected_text=selection_text,
        selected_party=request.selected_party,
        limit=TOP_K_CHUNKS,
    )
    raw_signals = extract_basic_signals(chunks)
    facts, extraction_strategy, extraction_warnings = await _extract_facts_for_context(
        chunks=chunks,
        request=request,
        provider_settings=provider_settings,
        provider=provider,
        raw_signals=raw_signals,
    )
    text = _format_context_text(
        strategy="smart_context",
        primary_selection=selection_text or None,
        chunks=chunks,
        raw_signals=raw_signals,
        facts=facts,
        conflict_candidates=[],
    )
    return _finalize(
        strategy="smart_context",
        context_text=text,
        chunks=chunks,
        raw_signals=raw_signals,
        facts=facts,
        source_document_characters=source_chars,
        extraction_strategy=extraction_strategy,
        warnings=[*warnings, *extraction_warnings],
    )
