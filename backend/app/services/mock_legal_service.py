from datetime import UTC, datetime

from app.schemas.actions import ReplaceSelectionAction
from app.schemas.chat import LegalRequest, LegalResponse, LegalScenario
from app.schemas.document import DocumentContextMode
from app.services.action_validator import validate_replace_selection_action

RISK_REVIEW_PROPOSAL = (
    "Ответственность Исполнителя ограничивается размером фактически оплаченных "
    "Заказчиком услуг по настоящему договору, за исключением случаев умысла или "
    "грубой неосторожности."
)

CLAUSE_REWRITE_PROPOSAL = (
    "Стороны обязуются добросовестно исполнять обязательства по настоящему договору, "
    "своевременно обмениваться необходимой информацией и незамедлительно уведомлять "
    "друг друга о любых обстоятельствах, которые могут повлиять на исполнение договора."
)


def _created_at() -> str:
    return datetime.now(UTC).isoformat()


def _replace_selection_action(
    *,
    title: str,
    original_text: str,
    proposed_text: str,
    rationale: str,
) -> ReplaceSelectionAction:
    return ReplaceSelectionAction(
        type="replace_selection",
        title=title,
        original_text=original_text,
        proposed_text=proposed_text,
        rationale=rationale,
        created_at=_created_at(),
    )


async def run_mock_legal_scenario(request: LegalRequest) -> LegalResponse:
    warnings: list[str] = []
    context = request.document_context
    context_text = context.text.strip()

    if not context_text:
        warnings.append("Document context is empty.")

    if request.scenario == LegalScenario.CHAT:
        return LegalResponse(
            scenario=request.scenario,
            answer=(
                "Mock-ответ юридического ассистента. Использован режим контекста "
                f"'{context.mode}'. Реальный LLM пока не подключен."
            ),
            warnings=warnings,
        )

    if request.scenario == LegalScenario.RISK_REVIEW:
        suggested_actions: list[ReplaceSelectionAction] = []

        if context.mode == DocumentContextMode.SELECTION and context_text:
            action = _replace_selection_action(
                title="Уточнить ограничение ответственности",
                original_text=context.text,
                proposed_text=RISK_REVIEW_PROPOSAL,
                rationale=(
                    "Правка делает ограничение ответственности более определенным и "
                    "сохраняет исключения для умысла и грубой неосторожности."
                ),
            )
            warnings.extend(validate_replace_selection_action(action))
            suggested_actions.append(action)

        return LegalResponse(
            scenario=request.scenario,
            answer=(
                "Mock-анализ рисков: проверьте предел ответственности, исключения из "
                "ограничения ответственности, сроки уведомлений и баланс прав сторон. "
                f"Режим контекста: '{context.mode}'."
            ),
            suggested_actions=suggested_actions,
            warnings=warnings,
        )

    if request.scenario == LegalScenario.INCONSISTENCY_CHECK:
        return LegalResponse(
            scenario=request.scenario,
            answer=(
                "Mock-анализ противоречий: возможны неоднозначности в сроках исполнения, "
                "порядке уведомлений и распределении ответственности. Рекомендуется "
                "сверить определения сторон, даты, суммы и ссылки на разделы договора."
            ),
            warnings=warnings,
        )

    if request.scenario == LegalScenario.CLAUSE_REWRITE:
        suggested_actions = []

        if context_text:
            action = _replace_selection_action(
                title="Переработать юридический пункт",
                original_text=context.text,
                proposed_text=CLAUSE_REWRITE_PROPOSAL,
                rationale=(
                    "Правка делает пункт более формальным, конкретным и пригодным для "
                    "включения в договор."
                ),
            )
            warnings.extend(validate_replace_selection_action(action))
            suggested_actions.append(action)

        return LegalResponse(
            scenario=request.scenario,
            answer=(
                "Mock-переработка пункта подготовлена. Проверьте предложенную редакцию "
                "перед применением в Word."
            ),
            suggested_actions=suggested_actions,
            warnings=warnings,
        )

    return LegalResponse(
        scenario=request.scenario,
        answer="Mock-сценарий не распознан.",
        warnings=warnings,
    )
