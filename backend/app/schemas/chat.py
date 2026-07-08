from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.actions import ReplaceSelectionAction
from app.schemas.context import ContextMetadata
from app.schemas.document import DocumentContext
from app.schemas.providers import ProviderSettings


class LegalScenario(StrEnum):
    CHAT = "chat"
    RISK_REVIEW = "risk_review"
    INCONSISTENCY_CHECK = "inconsistency_check"
    CLAUSE_REWRITE = "clause_rewrite"


class LegalRequest(BaseModel):
    scenario: LegalScenario
    message: str
    document_context: DocumentContext
    provider: ProviderSettings | None = None
    selected_party: str | None = None


class Finding(BaseModel):
    type: str
    title: str
    severity: str | None = None
    explanation: str
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class LegalResponse(BaseModel):
    scenario: LegalScenario
    answer: str
    findings: list[Finding] = Field(default_factory=list)
    suggested_actions: list[ReplaceSelectionAction] = Field(default_factory=list)
    context_metadata: ContextMetadata | None = None
    warnings: list[str] = Field(default_factory=list)
