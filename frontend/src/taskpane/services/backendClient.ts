/* global RequestInit, Response, fetch, setTimeout */

import type {
  HealthResponse,
  LegalJobCreateResponse,
  LegalJobStatus,
  LegalJobStatusResponse,
  LegalRequest,
  LegalResponse,
} from "../types/backend";
import { appConfig } from "../config/appConfig";
import type { ReplaceSelectionAction } from "../types/actions";
import type { ProviderSettings } from "../types/provider";

const BACKEND_BASE_URL = appConfig.backendBaseUrl;
const BACKEND_DISPLAY_URL = appConfig.backendDisplayUrl;

type BackendProviderSettings = {
  provider: string;
  model?: string | null;
  base_url?: string | null;
  api_key?: string | null;
};

type BackendLegalRequest = {
  scenario: LegalRequest["scenario"];
  message: string;
  document_context: {
    mode: LegalRequest["documentContext"]["mode"];
    text: string;
    character_count: number;
    captured_at?: string | null;
    selection_text?: string | null;
    full_text?: string | null;
  };
  provider?: BackendProviderSettings | null;
  selected_party?: string | null;
};

type BackendReplaceSelectionAction = {
  type: "replace_selection";
  title: string;
  original_text: string;
  proposed_text: string;
  rationale: string;
  rationale_source?: "llm" | "fallback";
  created_at: string;
};

type BackendLegalResponse = {
  scenario: LegalResponse["scenario"];
  answer: string;
  findings?: {
    type: string;
    title: string;
    severity?: string | null;
    explanation: string;
    evidence_chunk_ids?: string[];
    recommendation?: string | null;
  }[];
  suggested_actions?: BackendReplaceSelectionAction[];
  context_metadata?: {
    strategy: string;
    chunks_used: number;
    raw_signals_used?: number;
    facts_used: number;
    conflict_candidates_used?: number;
    extraction_strategy?: string | null;
    total_context_characters: number;
    source_document_characters: number;
    source_chunks?: {
      chunk_id: string;
      title?: string | null;
      section_path?: string[];
      start_char: number;
      end_char: number;
    }[];
    warnings?: string[];
  } | null;
  warnings?: string[];
};

type BackendLegalJobCreateResponse = {
  job_id: string;
  status: LegalJobStatus;
};

type BackendLegalJobStatusResponse = {
  job_id: string;
  status: LegalJobStatus;
  created_at: string;
  updated_at: string;
  response?: BackendLegalResponse | null;
  error?: {
    error_code: string;
    message: string;
  } | null;
  warnings?: string[];
};

function toBackendProvider(provider?: ProviderSettings | null): BackendProviderSettings | null {
  if (!provider) {
    return null;
  }

  return {
    provider: provider.provider,
    model: provider.model,
    base_url: provider.baseUrl,
    api_key: provider.apiKey,
  };
}

function toBackendRequest(request: LegalRequest): BackendLegalRequest {
  const selectionText =
    "selectionText" in request.documentContext ? request.documentContext.selectionText : undefined;
  const fullText =
    "fullText" in request.documentContext ? request.documentContext.fullText : undefined;

  return {
    scenario: request.scenario,
    message: request.message,
    document_context: {
      mode: request.documentContext.mode,
      text: request.documentContext.text,
      character_count: request.documentContext.characterCount,
      captured_at: request.documentContext.capturedAt,
      selection_text: selectionText,
      full_text: fullText,
    },
    provider: toBackendProvider(request.provider),
    selected_party: request.selectedParty,
  };
}

function toFrontendAction(action: BackendReplaceSelectionAction): ReplaceSelectionAction {
  return {
    type: action.type,
    title: action.title,
    originalText: action.original_text,
    proposedText: action.proposed_text,
    rationale: action.rationale,
    rationaleSource: action.rationale_source || "llm",
    createdAt: action.created_at,
  };
}

function toFrontendResponse(response: BackendLegalResponse): LegalResponse {
  return {
    scenario: response.scenario,
    answer: response.answer,
    findings: (response.findings || []).map((finding) => ({
      type: finding.type,
      title: finding.title,
      severity: finding.severity,
      explanation: finding.explanation,
      evidenceChunkIds: finding.evidence_chunk_ids || [],
      recommendation: finding.recommendation,
    })),
    suggestedActions: (response.suggested_actions || []).map(toFrontendAction),
    contextMetadata: response.context_metadata
      ? {
          strategy: response.context_metadata.strategy,
          chunksUsed: response.context_metadata.chunks_used,
          rawSignalsUsed: response.context_metadata.raw_signals_used || 0,
          factsUsed: response.context_metadata.facts_used,
          conflictCandidatesUsed: response.context_metadata.conflict_candidates_used || 0,
          extractionStrategy: response.context_metadata.extraction_strategy,
          totalContextCharacters: response.context_metadata.total_context_characters,
          sourceDocumentCharacters: response.context_metadata.source_document_characters,
          sourceChunks: (response.context_metadata.source_chunks || []).map((chunk) => ({
            chunkId: chunk.chunk_id,
            title: chunk.title,
            sectionPath: chunk.section_path || [],
            startChar: chunk.start_char,
            endChar: chunk.end_char,
          })),
          warnings: response.context_metadata.warnings || [],
        }
      : null,
    warnings: response.warnings || [],
  };
}

function toFrontendJobCreate(response: BackendLegalJobCreateResponse): LegalJobCreateResponse {
  return {
    jobId: response.job_id,
    status: response.status,
  };
}

function toFrontendJobStatus(response: BackendLegalJobStatusResponse): LegalJobStatusResponse {
  return {
    jobId: response.job_id,
    status: response.status,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
    response: response.response ? toFrontendResponse(response.response) : null,
    error: response.error
      ? {
          errorCode: response.error.error_code,
          message: response.error.message,
        }
      : null,
    warnings: response.warnings || [],
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;

      if (detail && typeof detail === "object" && "message" in detail) {
        const errorCode =
          "error_code" in detail && detail.error_code ? `${String(detail.error_code)}: ` : "";
        return `${errorCode}${String(detail.message)}`;
      }

      return String(detail);
    }

    return JSON.stringify(payload, null, 2);
  } catch {
    return response.statusText || "Unknown backend error";
  }
}

async function fetchJson<TResponse>(path: string, init?: RequestInit): Promise<TResponse> {
  let response: Response;

  try {
    response = await fetch(`${BACKEND_BASE_URL}${path}`, init);
  } catch (error) {
    const body = typeof init?.body === "string" ? init.body : "";
    const isFullDocumentInconsistency =
      body.includes('"scenario":"inconsistency_check"') && body.includes('"full_text"');

    if (isFullDocumentInconsistency) {
      throw new Error(
        `Full-document inconsistency analysis did not return through the local dev proxy. The backend may still have completed the request, but the Office WebView/proxy connection was interrupted. Try again, or use Smart context/shorter document. Details: ${String(
          error
        )}`
      );
    }

    throw new Error(
      `Backend is unavailable through the local dev proxy. Start FastAPI at ${BACKEND_DISPLAY_URL}, then restart npm run dev so the Vite proxy is active. Details: ${String(
        error
      )}`
    );
  }

  if (!response.ok) {
    const details = await parseErrorResponse(response);
    throw new Error(`Backend request failed (${response.status}): ${details}`);
  }

  return response.json() as Promise<TResponse>;
}

export async function checkBackendHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export async function runLegalScenario(request: LegalRequest): Promise<LegalResponse> {
  const response = await fetchJson<BackendLegalResponse>("/api/legal/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(toBackendRequest(request)),
  });

  return toFrontendResponse(response);
}

export async function createLegalScenarioJob(
  request: LegalRequest
): Promise<LegalJobCreateResponse> {
  const response = await fetchJson<BackendLegalJobCreateResponse>("/api/legal/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(toBackendRequest(request)),
  });

  return toFrontendJobCreate(response);
}

export async function getLegalScenarioJob(jobId: string): Promise<LegalJobStatusResponse> {
  const response = await fetchJson<BackendLegalJobStatusResponse>(`/api/legal/jobs/${jobId}`);

  return toFrontendJobStatus(response);
}

export async function runLegalScenarioJob(
  request: LegalRequest,
  options?: {
    pollIntervalMs?: number;
    timeoutMs?: number;
    onStatus?: (job: LegalJobStatusResponse) => void;
  }
): Promise<LegalResponse> {
  const pollIntervalMs = options?.pollIntervalMs || 1500;
  const timeoutMs = options?.timeoutMs || 300000;
  const startedAt = Date.now();
  const createdJob = await createLegalScenarioJob(request);
  let lastJob: LegalJobStatusResponse = {
    jobId: createdJob.jobId,
    status: createdJob.status,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    response: null,
    error: null,
    warnings: [],
  };

  options?.onStatus?.(lastJob);

  while (Date.now() - startedAt < timeoutMs) {
    await delay(pollIntervalMs);
    lastJob = await getLegalScenarioJob(createdJob.jobId);
    options?.onStatus?.(lastJob);

    if (lastJob.status === "succeeded") {
      if (!lastJob.response) {
        throw new Error("Legal analysis job finished without a response.");
      }

      return lastJob.response;
    }

    if (lastJob.status === "failed") {
      const error = lastJob.error;
      throw new Error(
        error
          ? `Legal analysis job failed: ${error.errorCode}: ${error.message}`
          : "Legal analysis job failed."
      );
    }
  }

  throw new Error(`Legal analysis job timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
}
