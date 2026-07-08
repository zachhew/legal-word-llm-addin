from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.chat import LegalResponse


class LegalJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LegalJobError(BaseModel):
    error_code: str
    message: str


class LegalJobCreateResponse(BaseModel):
    job_id: str
    status: LegalJobStatus


class LegalJobStatusResponse(BaseModel):
    job_id: str
    status: LegalJobStatus
    created_at: str
    updated_at: str
    response: LegalResponse | None = None
    error: LegalJobError | None = None
    warnings: list[str] = Field(default_factory=list)
