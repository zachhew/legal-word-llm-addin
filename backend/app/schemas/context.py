from pydantic import BaseModel, Field

from app.schemas.document import DocumentContextMode

ContextMode = DocumentContextMode


class DocumentChunk(BaseModel):
    chunk_id: str
    title: str | None
    text: str
    section_path: list[str]
    start_char: int
    end_char: int
    character_count: int


class RawSignal(BaseModel):
    signal_id: str
    signal_type: str
    value: str
    chunk_id: str
    start: int | None = None
    end: int | None = None


class LegalFact(BaseModel):
    fact_id: str
    fact_type: str
    value: str
    normalized_value: str | None = None
    chunk_id: str
    quote: str | None = None
    confidence: float = 1.0


class ConflictCandidate(BaseModel):
    conflict_id: str
    fact_type: str
    facts: list[LegalFact]
    reason: str


class ContextSourceChunk(BaseModel):
    chunk_id: str
    title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    start_char: int
    end_char: int


class ContextMetadata(BaseModel):
    strategy: str
    chunks_used: int
    raw_signals_used: int = 0
    facts_used: int
    conflict_candidates_used: int = 0
    extraction_strategy: str | None = None
    total_context_characters: int
    source_document_characters: int
    source_chunks: list[ContextSourceChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BuiltContext(BaseModel):
    strategy: str
    context_text: str
    chunks: list[DocumentChunk]
    raw_signals: list[RawSignal] = Field(default_factory=list)
    facts: list[LegalFact]
    conflict_candidates: list[ConflictCandidate] = Field(default_factory=list)
    metadata: ContextMetadata
    warnings: list[str] = Field(default_factory=list)
