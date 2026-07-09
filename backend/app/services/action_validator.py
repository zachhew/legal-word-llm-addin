from app.schemas.actions import ReplaceSelectionAction

COMMENTARY_START_PATTERNS = (
    "переработан текст",
    "пункт переработан",
    "текст пункта переработан",
    "текст переработан",
    "пункт переписан",
    "уточнена терминология",
    "уточнены формулировки",
    "добавлено указание",
    "добавлена оговорка",
    "заменено на",
    "исключено указание",
    "правка ",
    "предложенная редакция подготовлена",
)


def _looks_like_rewrite_commentary(text: str) -> bool:
    normalized = " ".join(text.lower().strip().split())
    if not normalized:
        return False

    if any(normalized.startswith(pattern) for pattern in COMMENTARY_START_PATTERNS):
        return True

    commentary_markers = (
        "использованием более формального",
        "уточнена терминология",
        "заменено на",
        "добавлено указание",
        "переработан текст",
    )
    marker_count = sum(1 for marker in commentary_markers if marker in normalized)
    return marker_count >= 2


def validate_replace_selection_action(action: ReplaceSelectionAction) -> list[str]:
    warnings: list[str] = []

    if not action.original_text.strip():
        warnings.append("original_text is empty.")

    if not action.proposed_text.strip():
        warnings.append("proposed_text is empty.")

    if action.proposed_text == action.original_text:
        warnings.append("proposed_text must differ from original_text.")

    if not action.title.strip():
        warnings.append("title is empty.")

    if action.rationale_source != "fallback" and not action.rationale.strip():
        warnings.append("rationale is empty.")

    if _looks_like_rewrite_commentary(action.proposed_text):
        warnings.append(
            "proposed_text appears to describe the rewrite instead of containing replacement text."
        )

    return warnings
