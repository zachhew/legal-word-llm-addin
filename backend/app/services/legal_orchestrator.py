import logging
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from app.core.config import settings as app_settings
from app.core.errors import (
    InvalidLLMResponseError,
    MissingProviderSettingsError,
)
from app.providers.factory import get_llm_provider
from app.schemas.actions import ReplaceSelectionAction
from app.schemas.chat import Finding, LegalRequest, LegalResponse
from app.schemas.context import BuiltContext
from app.schemas.document import DocumentContextMode
from app.schemas.providers import ProviderSettings
from app.services.action_validator import validate_replace_selection_action
from app.services.context.context_builder import build_context
from app.services.mock_legal_service import run_mock_legal_scenario
from app.services.prompt_builder import build_legal_messages

logger = logging.getLogger(__name__)


def _created_at() -> str:
    return datetime.now(UTC).isoformat()


def _validate_provider_settings(settings: ProviderSettings) -> None:
    provider = settings.provider

    if provider == "mock":
        return

    if not settings.api_key or not settings.api_key.strip():
        raise MissingProviderSettingsError("API key is required for the selected provider.")

    if not settings.model or not settings.model.strip():
        raise MissingProviderSettingsError("Model is required for the selected provider.")

    if provider == "openai_compatible" and not (
        (settings.base_url and settings.base_url.strip())
        or app_settings.openai_compatible_base_url.strip()
    ):
        raise MissingProviderSettingsError(
            "Base URL is required for OpenAI-compatible provider."
        )


def _action_from_raw(raw_action: Any) -> ReplaceSelectionAction | None:
    if not isinstance(raw_action, dict):
        return None

    action_payload = {
        "type": raw_action.get("type", "replace_selection"),
        "title": raw_action.get("title", ""),
        "original_text": raw_action.get("original_text", ""),
        "proposed_text": raw_action.get("proposed_text", ""),
        "rationale": raw_action.get("rationale", ""),
        "created_at": raw_action.get("created_at") or _created_at(),
        "rationale_source": "llm",
    }

    try:
        return ReplaceSelectionAction.model_validate(action_payload)
    except ValidationError:
        return None


def _finding_from_raw(raw_finding: Any) -> Finding | None:
    if not isinstance(raw_finding, dict):
        return None

    finding_payload = {
        "type": raw_finding.get("type", ""),
        "title": raw_finding.get("title", ""),
        "severity": raw_finding.get("severity"),
        "explanation": raw_finding.get("explanation", ""),
        "evidence_chunk_ids": raw_finding.get("evidence_chunk_ids", []),
        "recommendation": raw_finding.get("recommendation"),
    }

    try:
        finding = Finding.model_validate(finding_payload)
    except ValidationError:
        return None

    if not finding.type.strip() or not finding.title.strip() or not finding.explanation.strip():
        return None

    return finding


def _selected_original_text(request: LegalRequest) -> str:
    context = request.document_context
    if context.selection_text:
        return context.selection_text
    if context.mode == DocumentContextMode.SELECTION:
        return context.text
    return ""


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
    return re.sub(r"\s*```$", "", cleaned).strip()


def _split_rewrite_answer(answer: str) -> tuple[str, str | None]:
    proposed_text = _strip_code_fences(answer)
    rationale: str | None = None

    rationale_match = re.search(
        r"\n?\s*(?:обоснование|пояснение|причина правки|почему изменено)\s*:\s*(.+)$",
        proposed_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if rationale_match:
        rationale = rationale_match.group(1).strip(" \n\r\t\"“”")
        proposed_text = proposed_text[: rationale_match.start()].strip()

    label_match = re.search(
        r"(?:предлагаемая редакция|новая редакция|переписанный пункт)\s*:\s*(.+)",
        proposed_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if label_match:
        proposed_text = label_match.group(1).strip()

    return proposed_text.strip(" \n\r\t\"“”"), rationale


def _fallback_clause_rewrite_action(
    *,
    answer: str,
    original_text: str,
    warnings: list[str],
) -> ReplaceSelectionAction | None:
    if not original_text.strip():
        return None

    proposed_text, rationale = _split_rewrite_answer(answer)
    action = ReplaceSelectionAction(
        type="replace_selection",
        title="Переписать выделенный пункт",
        original_text=original_text,
        proposed_text=proposed_text,
        rationale=rationale or "",
        created_at=_created_at(),
        rationale_source="llm" if rationale else "fallback",
    )
    action_warnings = validate_replace_selection_action(action)
    if action_warnings:
        warnings.extend(
            f"Clause rewrite fallback action: {warning}" for warning in action_warnings
        )
        return None

    return action


def _build_clause_rewrite_repair_messages(
    *,
    original_text: str,
    raw_response: dict,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Ты исправляешь JSON-ответ для сценария clause_rewrite. "
                "Верни строго валидный JSON object без markdown. "
                "Нужно вернуть ровно один suggested_actions[0] типа replace_selection. "
                "original_text должен точно совпадать с исходным текстом. "
                "proposed_text должен быть новой редакцией договорного пункта, которую можно "
                "вставить в Word вместо original_text. "
                "proposed_text НЕ должен быть описанием изменений, комментарием, объяснением "
                "или фразой вроде 'переработан текст пункта'. "
                "Объяснение изменений клади только в rationale."
            ),
        },
        {
            "role": "user",
            "content": (
                "Исходный текст для замены:\n"
                f"{original_text}\n\n"
                "Предыдущий невалидный JSON-ответ модели:\n"
                f"{raw_response}\n\n"
                "Верни JSON в формате: "
                '{"answer":"краткий ответ",'
                '"findings":[],'
                '"suggested_actions":[{"type":"replace_selection",'
                '"title":"Переписать выделенный пункт",'
                '"original_text":"...",'
                '"proposed_text":"новая редакция пункта",'
                '"rationale":"что именно улучшено и почему"}],'
                '"warnings":[]}'
            ),
        },
    ]


def _normalize_llm_response(
    raw_response: dict, request: LegalRequest, built_context: BuiltContext
) -> LegalResponse:
    warnings: list[str] = []
    raw_warnings = raw_response.get("warnings", [])

    if isinstance(raw_warnings, list):
        warnings.extend(str(warning) for warning in raw_warnings)

    raw_answer = raw_response.get("answer", "")
    answer = raw_answer if isinstance(raw_answer, str) and raw_answer.strip() else ""
    if not answer:
        answer = "LLM вернул ответ без текстового поля answer."
        warnings.append("LLM response answer is empty.")

    findings: list[Finding] = []
    raw_findings = raw_response.get("findings", [])
    if raw_findings is None:
        raw_findings = []
    if not isinstance(raw_findings, list):
        warnings.append("LLM response findings must be a list.")
        raw_findings = []

    for index, raw_finding in enumerate(raw_findings):
        finding = _finding_from_raw(raw_finding)
        if finding is None:
            warnings.append(f"Finding #{index + 1} has invalid structure.")
            continue
        findings.append(finding)

    suggested_actions: list[ReplaceSelectionAction] = []
    raw_actions = raw_response.get("suggested_actions", [])
    if not isinstance(raw_actions, list):
        warnings.append("LLM response suggested_actions must be a list.")
        raw_actions = []

    for index, raw_action in enumerate(raw_actions):
        action = _action_from_raw(raw_action)
        if action is None:
            warnings.append(f"Suggested action #{index + 1} has invalid structure.")
            continue

        action_warnings = validate_replace_selection_action(action)
        expected_original_text = _selected_original_text(request)

        if (
            expected_original_text
            and action.original_text != expected_original_text
        ):
            action_warnings.append(
                "original_text must exactly match selected document context."
            )

        if action_warnings:
            warnings.extend(
                f"Suggested action #{index + 1}: {warning}" for warning in action_warnings
            )
            continue

        suggested_actions.append(action)

    expected_original_text = _selected_original_text(request)
    if (
        request.scenario == "clause_rewrite"
        and not suggested_actions
        and expected_original_text
    ):
        fallback_action = _fallback_clause_rewrite_action(
            answer=answer,
            original_text=expected_original_text,
            warnings=warnings,
        )
        if fallback_action is not None:
            suggested_actions.append(fallback_action)

    return LegalResponse(
        scenario=request.scenario,
        answer=answer,
        findings=findings,
        suggested_actions=suggested_actions,
        context_metadata=built_context.metadata,
        warnings=[*warnings, *built_context.warnings],
    )


async def _repair_clause_rewrite_if_needed(
    *,
    response: LegalResponse,
    raw_response: dict,
    request: LegalRequest,
    built_context: BuiltContext,
    provider: Any,
    provider_settings: ProviderSettings,
    base_url: str | None,
) -> LegalResponse:
    original_text = _selected_original_text(request)
    if request.scenario != "clause_rewrite" or response.suggested_actions or not original_text:
        return response

    logger.warning(
        "Clause rewrite response did not contain a valid replacement action; requesting repair: "
        "provider=%s model=%s",
        provider_settings.provider,
        provider_settings.model,
    )
    repaired_raw_response = await provider.generate_json(
        messages=_build_clause_rewrite_repair_messages(
            original_text=original_text,
            raw_response=raw_response,
        ),
        api_key=provider_settings.api_key or "",
        model=provider_settings.model or "",
        base_url=base_url,
        temperature=0.0,
    )
    repaired_response = _normalize_llm_response(
        repaired_raw_response,
        request,
        built_context,
    )
    if repaired_response.suggested_actions:
        repaired_response.warnings.append(
            "Initial clause rewrite response did not contain valid replacement text; "
            "backend requested a corrected structured action."
        )
        return repaired_response

    return response


async def run_legal_scenario(request: LegalRequest) -> LegalResponse:
    started_at = perf_counter()
    provider_settings = request.provider or ProviderSettings(
        provider=app_settings.default_provider,
        model=app_settings.default_model,
    )
    provider = None

    if provider_settings.provider != "mock":
        _validate_provider_settings(provider_settings)
        provider = get_llm_provider(provider_settings.provider)

    built_context = await build_context(
        request,
        provider_settings=provider_settings,
        provider=provider,
    )
    logger.info(
        "Context built: scenario=%s provider=%s context_mode=%s strategy=%s "
        "chunks=%s raw_signals=%s facts=%s conflicts=%s context_chars=%s",
        request.scenario,
        provider_settings.provider,
        request.document_context.mode,
        built_context.metadata.strategy,
        built_context.metadata.chunks_used,
        built_context.metadata.raw_signals_used,
        built_context.metadata.facts_used,
        built_context.metadata.conflict_candidates_used,
        built_context.metadata.total_context_characters,
    )

    if provider_settings.provider == "mock":
        response = await run_mock_legal_scenario(request)
        response.context_metadata = built_context.metadata
        response.warnings.extend(built_context.warnings)
        logger.info(
            "Legal scenario completed with mock provider: scenario=%s duration_ms=%s",
            request.scenario,
            int((perf_counter() - started_at) * 1000),
        )
        return response

    if provider is None:
        response = await run_mock_legal_scenario(request)
        response.context_metadata = built_context.metadata
        response.warnings.extend(built_context.warnings)
        logger.info(
            "Legal scenario completed with fallback mock provider: scenario=%s duration_ms=%s",
            request.scenario,
            int((perf_counter() - started_at) * 1000),
        )
        return response

    base_url = provider_settings.base_url
    if provider_settings.provider == "openrouter" and not base_url:
        base_url = app_settings.openrouter_base_url
    if provider_settings.provider == "openai_compatible" and not base_url:
        base_url = app_settings.openai_compatible_base_url

    messages = build_legal_messages(request, built_context)
    prompt_length = sum(len(message.get("content", "")) for message in messages)
    logger.info(
        "Provider call started: scenario=%s provider=%s model=%s prompt_length=%s",
        request.scenario,
        provider_settings.provider,
        provider_settings.model,
        prompt_length,
    )
    raw_response = await provider.generate_json(
        messages=messages,
        api_key=provider_settings.api_key or "",
        model=provider_settings.model or "",
        base_url=base_url,
        temperature=app_settings.llm_temperature,
    )
    logger.info(
        "Provider call completed: scenario=%s provider=%s model=%s duration_ms=%s",
        request.scenario,
        provider_settings.provider,
        provider_settings.model,
        int((perf_counter() - started_at) * 1000),
    )

    try:
        response = _normalize_llm_response(raw_response, request, built_context)
        response = await _repair_clause_rewrite_if_needed(
            response=response,
            raw_response=raw_response,
            request=request,
            built_context=built_context,
            provider=provider,
            provider_settings=provider_settings,
            base_url=base_url,
        )
        logger.info(
            "Legal scenario normalized: scenario=%s provider=%s findings=%s "
            "suggested_actions=%s warnings=%s",
            request.scenario,
            provider_settings.provider,
            len(response.findings),
            len(response.suggested_actions),
            len(response.warnings),
        )
        return response
    except Exception as error:
        logger.exception(
            "LLM response normalization failed: scenario=%s provider=%s",
            request.scenario,
            provider_settings.provider,
        )
        raise InvalidLLMResponseError("LLM response could not be normalized.") from error
