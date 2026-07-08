from app.schemas.actions import ReplaceSelectionAction


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

    return warnings
