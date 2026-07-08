/* global HTMLSelectElement */

import * as React from "react";
import type { DocumentContextMode, WordDocumentSnapshot } from "../types/document";

const e = React.createElement;

type ContextPanelProps = {
  onReadFullDocument: () => void;
  onReadSelection: () => void;
  onContextModeChange: (mode: DocumentContextMode) => void;
  currentFullDocument: WordDocumentSnapshot | null;
  currentSelection: WordDocumentSnapshot | null;
  contextMode: DocumentContextMode;
  isLoading: boolean;
};

export function ContextPanel({
  onReadFullDocument,
  onReadSelection,
  onContextModeChange,
  currentFullDocument,
  currentSelection,
  contextMode,
  isLoading,
}: ContextPanelProps) {
  const fullDocumentCount = currentFullDocument ? currentFullDocument.characterCount : 0;
  const selectionCount = currentSelection ? currentSelection.characterCount : 0;

  return e(
    "section",
    { className: "section compact-section", "aria-labelledby": "document-context-title" },
    e("h2", { id: "document-context-title" }, "Контекст документа"),
    e(
      "dl",
      { className: "context-status" },
      e("div", null, e("dt", null, "Весь документ"), e("dd", null, fullDocumentCount)),
      e("div", null, e("dt", null, "Выделенный текст"), e("dd", null, selectionCount))
    ),
    e(
      "div",
      { className: "form-grid" },
      e("label", { htmlFor: "context-mode" }, "Режим контекста"),
      e(
        "select",
        {
          id: "context-mode",
          value: contextMode,
          disabled: isLoading,
          onChange: (event: React.ChangeEvent<HTMLSelectElement>) =>
            onContextModeChange(event.target.value as DocumentContextMode),
        },
        e("option", { value: "auto" }, "Авто, рекомендуется"),
        e("option", { value: "selection" }, "Только выделение"),
        e("option", { value: "full_document" }, "Весь документ"),
        e("option", { value: "smart_context" }, "Умный контекст")
      )
    ),
    e(
      "div",
      { className: "button-row" },
      e(
        "button",
        { type: "button", onClick: onReadSelection, disabled: isLoading },
        "Прочитать выделение"
      ),
      e(
        "button",
        {
          type: "button",
          onClick: onReadFullDocument,
          disabled: isLoading,
          className: "secondary-button",
        },
        "Прочитать документ"
      )
    )
  );
}
