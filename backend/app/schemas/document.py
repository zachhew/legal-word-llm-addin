from enum import StrEnum

from pydantic import BaseModel


class DocumentContextMode(StrEnum):
    AUTO = "auto"
    FULL_DOCUMENT = "full_document"
    SELECTION = "selection"
    SMART_CONTEXT = "smart_context"


class DocumentContext(BaseModel):
    mode: DocumentContextMode
    text: str
    character_count: int
    captured_at: str | None = None
    selection_text: str | None = None
    full_text: str | None = None
