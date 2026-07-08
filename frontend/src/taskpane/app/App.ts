/* global console, HTMLTextAreaElement */

import * as React from "react";
import { useState } from "react";
import { ContextPanel } from "../components/ContextPanel";
import { ContextMetadataPanel } from "../components/ContextMetadataPanel";
import { FindingsPanel } from "../components/FindingsPanel";
import { OutputPanel } from "../components/OutputPanel";
import { ProviderSettingsPanel } from "../components/ProviderSettingsPanel";
import { SuggestedChangeCard } from "../components/SuggestedChangeCard";
import {
  checkBackendHealth,
  runLegalScenario,
  runLegalScenarioJob,
} from "../services/backendClient";
import { applyDocumentAction } from "../services/documentActionService";
import { readFullDocument, readSelection } from "../services/wordDocumentService";
import type { DocumentAction } from "../types/actions";
import type {
  ContextMetadata,
  DocumentContext,
  Finding,
  LegalResponse,
  LegalScenario,
} from "../types/backend";
import type { DocumentContextMode, WordDocumentSnapshot } from "../types/document";
import { DEFAULT_PROVIDER_SETTINGS, type ProviderSettings } from "../types/provider";

const e = React.createElement;

const SCENARIO_LABELS: Record<LegalScenario, string> = {
  chat: "Чат",
  risk_review: "Проверка рисков",
  inconsistency_check: "Поиск противоречий",
  clause_rewrite: "Переписывание пункта",
};

function formatSnapshot(snapshot: WordDocumentSnapshot): string {
  const label =
    snapshot.mode === "full_document"
      ? "Весь документ"
      : snapshot.mode === "selection"
        ? "Выделенный текст"
        : snapshot.mode === "auto"
          ? "Автоконтекст"
          : "Умный контекст";

  return `${label}
Время чтения: ${snapshot.capturedAt}
Количество символов: ${snapshot.characterCount}

${snapshot.text || "(пусто)"}`;
}

function formatLegalResponse(response: LegalResponse): string {
  const warnings = response.warnings.length
    ? `\n\nПредупреждения:\n${response.warnings.map((warning) => `- ${warning}`).join("\n")}`
    : "";
  const actionSummary = response.suggestedActions.length
    ? `\n\nПредложенных правок: ${response.suggestedActions.length}`
    : "\n\nПредложенных правок нет.";
  const findingsSummary = response.findings.length
    ? `\nВыводов: ${response.findings.length}`
    : "\nВыводов нет.";

  return `Сценарий: ${SCENARIO_LABELS[response.scenario]}

${response.answer}${findingsSummary}${actionSummary}${warnings}`;
}

function formatContextStatus(
  currentSelection: WordDocumentSnapshot | null,
  currentFullDocument: WordDocumentSnapshot | null
): string {
  if (currentSelection && currentSelection.text.trim()) {
    return `Будет использован выделенный текст: ${currentSelection.characterCount} символов.`;
  }

  if (currentFullDocument && currentFullDocument.text.trim()) {
    return `Будет использован весь документ: ${currentFullDocument.characterCount} символов.`;
  }

  return "Сначала прочитайте выделенный текст или весь документ.";
}

function validateProviderSettings(settings: ProviderSettings): string | null {
  if (settings.provider === "mock") {
    return null;
  }

  if (!settings.model.trim()) {
    return "Укажите модель LLM-провайдера.";
  }

  if (!settings.apiKey || !settings.apiKey.trim()) {
    return "Укажите API key для выбранного LLM-провайдера.";
  }

  if (settings.provider === "openai_compatible" && !(settings.baseUrl || "").trim()) {
    return "Укажите Base URL для OpenAI-compatible провайдера.";
  }

  return null;
}

function createDocumentContext(
  mode: DocumentContextMode,
  primary: WordDocumentSnapshot,
  currentSelection: WordDocumentSnapshot | null,
  currentFullDocument: WordDocumentSnapshot | null
): DocumentContext {
  const selectionText =
    currentSelection && currentSelection.text.trim() ? currentSelection.text : null;
  const fullText =
    currentFullDocument && currentFullDocument.text.trim() ? currentFullDocument.text : null;

  return {
    mode,
    text: primary.text,
    characterCount: primary.text.length,
    capturedAt: primary.capturedAt,
    selectionText,
    fullText,
  };
}

function selectChatSnapshot(
  mode: DocumentContextMode,
  currentSelection: WordDocumentSnapshot | null,
  currentFullDocument: WordDocumentSnapshot | null
): WordDocumentSnapshot | null {
  if (mode === "selection") {
    return currentSelection;
  }

  if (mode === "full_document") {
    return currentFullDocument;
  }

  return currentSelection && currentSelection.text.trim() ? currentSelection : currentFullDocument;
}

export function App() {
  const [output, setOutput] = useState<string>(
    "Готово. Прочитайте документ или выделенный текст в Word."
  );
  const [currentFullDocument, setCurrentFullDocument] = useState<WordDocumentSnapshot | null>(null);
  const [currentSelection, setCurrentSelection] = useState<WordDocumentSnapshot | null>(null);
  const [contextMode, setContextMode] = useState<DocumentContextMode>("auto");
  const [providerSettings, setProviderSettings] =
    useState<ProviderSettings>(DEFAULT_PROVIDER_SETTINGS);
  const [userMessage, setUserMessage] = useState<string>("");
  const [proposedText, setProposedText] = useState<string>("");
  const [pendingAction, setPendingAction] = useState<DocumentAction | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [contextMetadata, setContextMetadata] = useState<ContextMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const contextStatus = formatContextStatus(currentSelection, currentFullDocument);

  async function runAsync(handler: () => Promise<void>): Promise<void> {
    setIsLoading(true);
    setError(null);

    try {
      await handler();
    } catch (caughtError) {
      console.error(caughtError);
      const message = String(caughtError);
      setError(message);
      setOutput(`Ошибка:\n${message}`);
    } finally {
      setIsLoading(false);
    }
  }

  function showError(message: string): void {
    setError(message);
    setOutput(message);
  }

  function clearAnalysisPanels(): void {
    setFindings([]);
    setContextMetadata(null);
  }

  function handleReadFullDocument(): Promise<void> {
    return runAsync(async () => {
      const snapshot = await readFullDocument();
      setCurrentFullDocument(snapshot);
      clearAnalysisPanels();
      setOutput(formatSnapshot(snapshot));
    });
  }

  function handleReadSelection(): Promise<void> {
    return runAsync(async () => {
      const snapshot = await readSelection();
      setCurrentSelection(snapshot);
      setPendingAction(null);
      clearAnalysisPanels();
      setOutput(formatSnapshot(snapshot));

      if (!snapshot.text.trim()) {
        showError("В Word нет выделенного текста. Выделите фрагмент документа и повторите чтение.");
      }
    });
  }

  function handleCreateReplacementProposal(): void {
    setError(null);

    if (!currentSelection) {
      showError("Сначала прочитайте выделенный текст.");
      return;
    }

    if (currentSelection.mode !== "selection") {
      showError("Предложение замены можно создать только для выделенного текста.");
      return;
    }

    if (!currentSelection.text.trim()) {
      showError("Нельзя создать предложение замены для пустого выделения.");
      return;
    }

    if (!proposedText.trim()) {
      showError("Введите текст предлагаемой замены.");
      return;
    }

    const action: DocumentAction = {
      type: "replace_selection",
      title: "Заменить выбранный фрагмент",
      originalText: currentSelection.text,
      proposedText,
      rationale: "Ручное предложение замены создано до подключения LLM.",
      createdAt: new Date().toISOString(),
    };

    setPendingAction(action);
    setOutput("Предложение замены создано. Проверьте его перед применением.");
  }

  function handleTestBackend(): Promise<void> {
    return runAsync(async () => {
      const health = await checkBackendHealth();
      setOutput(JSON.stringify(health, null, 2));
    });
  }

  function handleRunLegalScenario(
    scenario: LegalScenario,
    message: string,
    documentContext: DocumentContext
  ): Promise<void> {
    return runAsync(async () => {
      const providerError = validateProviderSettings(providerSettings);
      if (providerError) {
        showError(providerError);
        return;
      }

      const response = await runLegalScenario({
        scenario,
        message,
        documentContext,
        provider: providerSettings,
      });

      setPendingAction(response.suggestedActions[0] || null);
      setFindings(response.findings);
      setContextMetadata(response.contextMetadata || null);
      setOutput(formatLegalResponse(response));
    });
  }

  function handleRunChat(): Promise<void> {
    const snapshot = selectChatSnapshot(contextMode, currentSelection, currentFullDocument);

    if (!snapshot || !snapshot.text.trim()) {
      showError("Сначала прочитайте выделенный текст или весь документ.");
      return Promise.resolve();
    }

    const message = userMessage.trim() || "Ответь на вопрос по переданному юридическому контексту.";
    return handleRunLegalScenario(
      "chat",
      message,
      createDocumentContext(contextMode, snapshot, currentSelection, currentFullDocument)
    );
  }

  function handleRiskReview(): Promise<void> {
    if (!currentSelection || !currentSelection.text.trim()) {
      showError("Сначала нажмите «Прочитать выделенный текст».");
      return Promise.resolve();
    }

    return handleRunLegalScenario(
      "risk_review",
      "Проверь выделенный пункт на юридические риски.",
      createDocumentContext(contextMode, currentSelection, currentSelection, currentFullDocument)
    );
  }

  function handleClauseRewrite(): Promise<void> {
    if (!currentSelection || !currentSelection.text.trim()) {
      showError("Сначала нажмите «Прочитать выделенный текст».");
      return Promise.resolve();
    }

    return handleRunLegalScenario(
      "clause_rewrite",
      "Перепиши выделенный пункт юридическим языком.",
      createDocumentContext(contextMode, currentSelection, currentSelection, currentFullDocument)
    );
  }

  function handleInconsistencyCheck(): Promise<void> {
    return runAsync(async () => {
      let fullDocument = currentFullDocument;

      if (!fullDocument || !fullDocument.text.trim()) {
        fullDocument = await readFullDocument();
        setCurrentFullDocument(fullDocument);
      }

      if (!fullDocument.text.trim()) {
        showError("Документ пустой. Нечего проверять на противоречия.");
        return;
      }

      const providerError = validateProviderSettings(providerSettings);
      if (providerError) {
        showError(providerError);
        return;
      }

      const response = await runLegalScenarioJob(
        {
          scenario: "inconsistency_check",
          message: "Проверь документ на противоречия и неоднозначности.",
          documentContext: createDocumentContext(
            contextMode,
            fullDocument,
            currentSelection,
            fullDocument
          ),
          provider: providerSettings,
        },
        {
          onStatus: (job) => {
            const statusText =
              job.status === "queued"
                ? "Задача поставлена в очередь."
                : job.status === "running"
                  ? "Backend анализирует документ. Соединение не держится открытым."
                  : job.status === "succeeded"
                    ? "Анализ завершен."
                    : "Анализ завершился ошибкой.";
            setOutput(`Поиск противоречий:\n${statusText}\n\nJob ID: ${job.jobId}`);
          },
        }
      );

      setPendingAction(response.suggestedActions[0] || null);
      setFindings(response.findings);
      setContextMetadata(response.contextMetadata || null);
      setOutput(formatLegalResponse(response));
    });
  }

  function handleApplyChange(): Promise<void> {
    return runAsync(async () => {
      if (!pendingAction) {
        showError("Нет ожидающей правки для применения.");
        return;
      }

      const result = await applyDocumentAction(pendingAction);
      setOutput(result.message);

      if (result.success) {
        setPendingAction(null);
        setProposedText("");
      }
    });
  }

  function handleRejectChange(): void {
    setPendingAction(null);
    clearAnalysisPanels();
    setOutput("Предложение правки отклонено.");
    setError(null);
  }

  return e(
    "main",
    { className: "app" },
    e(
      "header",
      { className: "app-header" },
      e("h1", null, "Юридический LLM-ассистент"),
      e("p", null, "Помощник Word для проверки юридических документов")
    ),
    e(ContextPanel, {
      currentFullDocument,
      currentSelection,
      contextMode,
      onContextModeChange: setContextMode,
      isLoading,
      onReadFullDocument: handleReadFullDocument,
      onReadSelection: handleReadSelection,
    }),
    e(
      "section",
      { className: "section primary-section", "aria-labelledby": "assistant-actions-title" },
      e("h2", { id: "assistant-actions-title" }, "Юридическая проверка"),
      e("p", { className: "context-hint" }, contextStatus),
      e("label", { htmlFor: "chat-message" }, "Вопрос к ассистенту"),
      e("textarea", {
        id: "chat-message",
        value: userMessage,
        rows: 4,
        onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) =>
          setUserMessage(event.target.value),
        disabled: isLoading,
        placeholder: "Например: какие риски есть для Заказчика?",
      }),
      e(
        "div",
        { className: "button-stack" },
        e(
          "button",
          { type: "button", onClick: handleRunChat, disabled: isLoading },
          "Задать вопрос"
        ),
        e(
          "button",
          { type: "button", onClick: handleRiskReview, disabled: isLoading },
          "Проверить риски"
        ),
        e(
          "button",
          { type: "button", onClick: handleInconsistencyCheck, disabled: isLoading },
          "Найти противоречия"
        ),
        e(
          "button",
          { type: "button", onClick: handleClauseRewrite, disabled: isLoading },
          "Переписать пункт"
        )
      )
    ),
    pendingAction
      ? e(SuggestedChangeCard, {
          action: pendingAction,
          isLoading,
          onApply: handleApplyChange,
          onReject: handleRejectChange,
        })
      : null,
    e(FindingsPanel, { findings, contextMetadata }),
    e(ContextMetadataPanel, { metadata: contextMetadata }),
    e(OutputPanel, { output, error, isLoading }),
    e(ProviderSettingsPanel, {
      settings: providerSettings,
      onChange: setProviderSettings,
      isLoading,
    }),
    e(
      "details",
      { className: "section details-section" },
      e("summary", null, "Ручная правка"),
      e("label", { htmlFor: "proposed-text" }, "Текст для замены"),
      e("textarea", {
        id: "proposed-text",
        value: proposedText,
        rows: 7,
        onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) =>
          setProposedText(event.target.value),
        disabled: isLoading,
      }),
      e(
        "button",
        { type: "button", onClick: handleCreateReplacementProposal, disabled: isLoading },
        "Создать предложение замены"
      )
    ),
    e(
      "details",
      { className: "section details-section" },
      e("summary", null, "Диагностика"),
      e(
        "button",
        {
          type: "button",
          onClick: handleTestBackend,
          disabled: isLoading,
          className: "secondary-button",
        },
        "Проверить backend"
      )
    )
  );
}
