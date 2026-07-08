import type { ReplaceSelectionAction } from "./actions";
import type { DocumentContextMode, WordDocumentSnapshot } from "./document";
import type { ProviderSettings } from "./provider";

export type HealthResponse = {
  status: string;
  service: string;
};

export type LegalScenario = "chat" | "risk_review" | "inconsistency_check" | "clause_rewrite";

export type DocumentContext = {
  mode: DocumentContextMode;
  text: string;
  characterCount: number;
  capturedAt?: string | null;
  selectionText?: string | null;
  fullText?: string | null;
};

export type Finding = {
  type: string;
  title: string;
  severity?: string | null;
  explanation: string;
  evidenceChunkIds: string[];
  recommendation?: string | null;
};

export type ContextMetadata = {
  strategy: string;
  chunksUsed: number;
  rawSignalsUsed: number;
  factsUsed: number;
  conflictCandidatesUsed: number;
  extractionStrategy?: string | null;
  totalContextCharacters: number;
  sourceDocumentCharacters: number;
  sourceChunks: {
    chunkId: string;
    title?: string | null;
    sectionPath: string[];
    startChar: number;
    endChar: number;
  }[];
  warnings: string[];
};

export type LegalRequest = {
  scenario: LegalScenario;
  message: string;
  documentContext: DocumentContext | WordDocumentSnapshot;
  provider?: ProviderSettings | null;
  selectedParty?: string | null;
};

export type LegalResponse = {
  scenario: LegalScenario;
  answer: string;
  findings: Finding[];
  suggestedActions: ReplaceSelectionAction[];
  contextMetadata?: ContextMetadata | null;
  warnings: string[];
};

export type LegalJobStatus = "queued" | "running" | "succeeded" | "failed";

export type LegalJobCreateResponse = {
  jobId: string;
  status: LegalJobStatus;
};

export type LegalJobStatusResponse = {
  jobId: string;
  status: LegalJobStatus;
  createdAt: string;
  updatedAt: string;
  response?: LegalResponse | null;
  error?: {
    errorCode: string;
    message: string;
  } | null;
  warnings: string[];
};
