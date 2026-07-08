from app.core.config import get_settings
from app.core.errors import RequestTooLargeError
from app.schemas.chat import LegalRequest


def _validate_text_size(label: str, value: str | None, max_chars: int) -> None:
    if value is not None and len(value) > max_chars:
        raise RequestTooLargeError(
            f"{label} is too large: {len(value)} characters, limit is {max_chars}."
        )


def validate_legal_request_size(request: LegalRequest) -> None:
    settings = get_settings()
    context = request.document_context

    _validate_text_size("document_context.text", context.text, settings.max_document_text_chars)
    _validate_text_size(
        "document_context.full_text",
        context.full_text,
        settings.max_document_text_chars,
    )
    _validate_text_size(
        "document_context.selection_text",
        context.selection_text,
        settings.max_selection_text_chars,
    )
