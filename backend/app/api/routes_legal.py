import logging
from time import perf_counter

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
logger = logging.getLogger(__name__)


def _provider_name(request: LegalRequest) -> str:
    return request.provider.provider if request.provider else "default"


def _provider_model(request: LegalRequest) -> str | None:
    return request.provider.model if request.provider else None


def _document_lengths(request: LegalRequest) -> dict[str, int]:
    context = request.document_context
    return {
        "document_length": len(context.text or ""),
        "selection_length": len(context.selection_text or ""),
        "full_text_length": len(context.full_text or ""),
    }


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
    started_at = perf_counter()
    lengths = _document_lengths(request)
    logger.info(
        "Legal request started: endpoint=/api/legal/run scenario=%s provider=%s model=%s "
        "context_mode=%s document_length=%s selection_length=%s full_text_length=%s",
        request.scenario,
        _provider_name(request),
        _provider_model(request),
        request.document_context.mode,
        lengths["document_length"],
        lengths["selection_length"],
        lengths["full_text_length"],
    )
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
        response = await orchestrate_legal_scenario(request)
        duration_ms = int((perf_counter() - started_at) * 1000)
        metadata = response.context_metadata
        logger.info(
            "Legal request completed: endpoint=/api/legal/run scenario=%s provider=%s "
            "duration_ms=%s context_strategy=%s chunks=%s facts=%s conflicts=%s",
            request.scenario,
            _provider_name(request),
            duration_ms,
            metadata.strategy if metadata else None,
            metadata.chunks_used if metadata else None,
            metadata.facts_used if metadata else None,
            metadata.conflict_candidates_used if metadata else None,
        )
        return response
    except RequestTooLargeError as error:
        logger.warning(
            "Legal request rejected: endpoint=/api/legal/run scenario=%s error_code=%s",
            request.scenario,
            "REQUEST_TOO_LARGE",
        )
        raise HTTPException(
            status_code=413,
            detail=_error_detail("REQUEST_TOO_LARGE", str(error)),
        ) from error
    except MissingProviderSettingsError as error:
        logger.warning(
            "Legal request rejected: endpoint=/api/legal/run scenario=%s provider=%s "
            "error_code=%s",
            request.scenario,
            _provider_name(request),
            "MISSING_PROVIDER_SETTINGS",
        )
        raise HTTPException(
            status_code=400,
            detail=_error_detail("MISSING_PROVIDER_SETTINGS", str(error)),
        ) from error
    except InvalidLLMResponseError as error:
        logger.exception(
            "Legal request failed: endpoint=/api/legal/run scenario=%s provider=%s "
            "error_code=%s",
            request.scenario,
            _provider_name(request),
            "INVALID_LLM_RESPONSE",
        )
        raise HTTPException(
            status_code=502,
            detail=_error_detail("INVALID_LLM_RESPONSE", str(error)),
        ) from error
    except LLMProviderError as error:
        logger.exception(
            "Legal request failed: endpoint=/api/legal/run scenario=%s provider=%s "
            "error_code=%s",
            request.scenario,
            _provider_name(request),
            "LLM_PROVIDER_ERROR",
        )
        raise HTTPException(
            status_code=502,
            detail=_error_detail("LLM_PROVIDER_ERROR", str(error)),
        ) from error
    except ValueError as error:
        logger.warning(
            "Legal request rejected: endpoint=/api/legal/run scenario=%s provider=%s "
            "error_code=%s",
            request.scenario,
            _provider_name(request),
            "UNSUPPORTED_PROVIDER",
        )
        raise HTTPException(
            status_code=400,
            detail=_error_detail("UNSUPPORTED_PROVIDER", str(error)),
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "Legal request failed: endpoint=/api/legal/run scenario=%s error_code=%s",
            request.scenario,
            "INTERNAL_SERVER_ERROR",
        )
        raise HTTPException(
            status_code=500,
            detail=_error_detail("INTERNAL_SERVER_ERROR", "Unexpected backend error."),
        ) from error


@router.post("/jobs", response_model=LegalJobCreateResponse)
async def create_legal_analysis_job(
    request: LegalRequest,
    background_tasks: BackgroundTasks,
) -> LegalJobCreateResponse:
    lengths = _document_lengths(request)
    logger.info(
        "Legal job create requested: scenario=%s provider=%s model=%s context_mode=%s "
        "document_length=%s selection_length=%s full_text_length=%s",
        request.scenario,
        _provider_name(request),
        _provider_model(request),
        request.document_context.mode,
        lengths["document_length"],
        lengths["selection_length"],
        lengths["full_text_length"],
    )
    try:
        validate_legal_request_size(request)
        job = create_legal_job()
        logger.info(
            "Legal job created: job_id=%s scenario=%s provider=%s",
            job.job_id,
            request.scenario,
            _provider_name(request),
        )
        background_tasks.add_task(run_legal_job, job.job_id, request)
        return job
    except RequestTooLargeError as error:
        logger.warning(
            "Legal job rejected: scenario=%s error_code=%s",
            request.scenario,
            "REQUEST_TOO_LARGE",
        )
        raise HTTPException(
            status_code=413,
            detail=_error_detail("REQUEST_TOO_LARGE", str(error)),
        ) from error


@router.get("/jobs/{job_id}", response_model=LegalJobStatusResponse)
async def get_legal_analysis_job(job_id: str) -> LegalJobStatusResponse:
    job = get_legal_job(job_id)
    if job is None:
        logger.warning("Legal job not found: job_id=%s", job_id)
        raise HTTPException(
            status_code=404,
            detail=_error_detail("JOB_NOT_FOUND", "Legal analysis job was not found."),
        )

    logger.info("Legal job status requested: job_id=%s status=%s", job_id, job.status)
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
