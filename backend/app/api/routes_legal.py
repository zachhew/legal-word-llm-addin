from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.errors import (
    InvalidLLMResponseError,
    LLMProviderError,
    MissingProviderSettingsError,
    RequestTooLargeError,
)
from app.schemas.chat import LegalRequest, LegalResponse, LegalScenario
from app.schemas.context import BuiltContext
from app.schemas.jobs import LegalJobCreateResponse, LegalJobStatusResponse
from app.services.context.context_builder import build_context
from app.services.legal_job_service import create_legal_job, get_legal_job, run_legal_job
from app.services.legal_orchestrator import run_legal_scenario as orchestrate_legal_scenario
from app.services.request_limits import validate_legal_request_size

router = APIRouter(prefix="/api/legal", tags=["legal"])


def _error_detail(error_code: str, message: str) -> dict[str, str]:
    return {
        "error_code": error_code,
        "message": message,
    }


def _requires_job_endpoint(request: LegalRequest) -> bool:
    context = request.document_context
    return (
        request.scenario == LegalScenario.INCONSISTENCY_CHECK
        and bool(context.full_text and context.full_text.strip())
    )


@router.post("/run", response_model=LegalResponse)
async def run_legal_scenario(request: LegalRequest) -> LegalResponse:
    try:
        validate_legal_request_size(request)
        if _requires_job_endpoint(request):
            raise HTTPException(
                status_code=409,
                detail=_error_detail(
                    "USE_JOB_ENDPOINT",
                    (
                        "Full-document inconsistency analysis must use "
                        "POST /api/legal/jobs and polling."
                    ),
                ),
            )
        return await orchestrate_legal_scenario(request)
    except RequestTooLargeError as error:
        raise HTTPException(
            status_code=413,
            detail=_error_detail("REQUEST_TOO_LARGE", str(error)),
        ) from error
    except MissingProviderSettingsError as error:
        raise HTTPException(
            status_code=400,
            detail=_error_detail("MISSING_PROVIDER_SETTINGS", str(error)),
        ) from error
    except InvalidLLMResponseError as error:
        raise HTTPException(
            status_code=502,
            detail=_error_detail("INVALID_LLM_RESPONSE", str(error)),
        ) from error
    except LLMProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=_error_detail("LLM_PROVIDER_ERROR", str(error)),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_error_detail("UNSUPPORTED_PROVIDER", str(error)),
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=_error_detail("INTERNAL_SERVER_ERROR", "Unexpected backend error."),
        ) from error


@router.post("/jobs", response_model=LegalJobCreateResponse)
async def create_legal_analysis_job(
    request: LegalRequest,
    background_tasks: BackgroundTasks,
) -> LegalJobCreateResponse:
    try:
        validate_legal_request_size(request)
        job = create_legal_job()
        background_tasks.add_task(run_legal_job, job.job_id, request)
        return job
    except RequestTooLargeError as error:
        raise HTTPException(
            status_code=413,
            detail=_error_detail("REQUEST_TOO_LARGE", str(error)),
        ) from error


@router.get("/jobs/{job_id}", response_model=LegalJobStatusResponse)
async def get_legal_analysis_job(job_id: str) -> LegalJobStatusResponse:
    job = get_legal_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=_error_detail("JOB_NOT_FOUND", "Legal analysis job was not found."),
        )

    return job


@router.post("/context-debug", response_model=BuiltContext)
async def debug_context(request: LegalRequest) -> BuiltContext:
    validate_legal_request_size(request)
    return await build_context(request)


@router.post("/risk-review", response_model=LegalResponse)
async def run_risk_review(request: LegalRequest) -> LegalResponse:
    scenario_request = request.model_copy(update={"scenario": LegalScenario.RISK_REVIEW})
    return await run_legal_scenario(scenario_request)


@router.post("/rewrite-clause", response_model=LegalResponse)
async def run_rewrite_clause(request: LegalRequest) -> LegalResponse:
    scenario_request = request.model_copy(update={"scenario": LegalScenario.CLAUSE_REWRITE})
    return await run_legal_scenario(scenario_request)
