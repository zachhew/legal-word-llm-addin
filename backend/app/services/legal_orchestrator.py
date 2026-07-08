import re
from datetime import UTC, datetime
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


async def run_legal_scenario(request: LegalRequest) -> LegalResponse:
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

    if provider_settings.provider == "mock":
        response = await run_mock_legal_scenario(request)
        response.context_metadata = built_context.metadata
        response.warnings.extend(built_context.warnings)
        return response

    if provider is None:
        response = await run_mock_legal_scenario(request)
        response.context_metadata = built_context.metadata
        response.warnings.extend(built_context.warnings)
        return response

    base_url = provider_settings.base_url
    if provider_settings.provider == "openrouter" and not base_url:
        base_url = app_settings.openrouter_base_url
    if provider_settings.provider == "openai_compatible" and not base_url:
        base_url = app_settings.openai_compatible_base_url

    messages = build_legal_messages(request, built_context)
    raw_response = await provider.generate_json(
        messages=messages,
        api_key=provider_settings.api_key or "",
        model=provider_settings.model or "",
        base_url=base_url,
        temperature=app_settings.llm_temperature,
    )

    try:
        return _normalize_llm_response(raw_response, request, built_context)
    except Exception as error:
        raise InvalidLLMResponseError("LLM response could not be normalized.") from error
