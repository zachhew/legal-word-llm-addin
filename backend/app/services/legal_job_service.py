from datetime import UTC, datetime
from uuid import uuid4

from app.core.errors import (
    InvalidLLMResponseError,
    LLMProviderError,
    MissingProviderSettingsError,
)
from app.schemas.chat import LegalRequest
from app.schemas.jobs import (
    LegalJobCreateResponse,
    LegalJobError,
    LegalJobStatus,
    LegalJobStatusResponse,
)
from app.services.legal_orchestrator import run_legal_scenario

_jobs: dict[str, LegalJobStatusResponse] = {}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_legal_job() -> LegalJobCreateResponse:
    job_id = f"legal_job_{uuid4().hex}"
    timestamp = _now()
    _jobs[job_id] = LegalJobStatusResponse(
        job_id=job_id,
        status=LegalJobStatus.QUEUED,
        created_at=timestamp,
        updated_at=timestamp,
    )
    return LegalJobCreateResponse(job_id=job_id, status=LegalJobStatus.QUEUED)


def get_legal_job(job_id: str) -> LegalJobStatusResponse | None:
    return _jobs.get(job_id)


def _set_job_status(
    job_id: str,
    status: LegalJobStatus,
    *,
    response=None,
    error: LegalJobError | None = None,
    warnings: list[str] | None = None,
) -> None:
    current = _jobs[job_id]
    _jobs[job_id] = current.model_copy(
        update={
            "status": status,
            "updated_at": _now(),
            "response": response,
            "error": error,
            "warnings": warnings or current.warnings,
        }
    )


def _error_from_exception(error: Exception) -> LegalJobError:
    if isinstance(error, MissingProviderSettingsError):
        return LegalJobError(error_code="MISSING_PROVIDER_SETTINGS", message=str(error))
    if isinstance(error, InvalidLLMResponseError):
        return LegalJobError(error_code="INVALID_LLM_RESPONSE", message=str(error))
    if isinstance(error, LLMProviderError):
        return LegalJobError(error_code="LLM_PROVIDER_ERROR", message=str(error))
    if isinstance(error, ValueError):
        return LegalJobError(error_code="UNSUPPORTED_PROVIDER", message=str(error))

    return LegalJobError(
        error_code="INTERNAL_SERVER_ERROR",
        message="Unexpected backend error.",
    )


async def run_legal_job(job_id: str, request: LegalRequest) -> None:
    _set_job_status(job_id, LegalJobStatus.RUNNING)

    try:
        response = await run_legal_scenario(request)
    except Exception as error:
        _set_job_status(
            job_id,
            LegalJobStatus.FAILED,
            error=_error_from_exception(error),
        )
        return

    _set_job_status(
        job_id,
        LegalJobStatus.SUCCEEDED,
        response=response,
        warnings=response.warnings,
    )
