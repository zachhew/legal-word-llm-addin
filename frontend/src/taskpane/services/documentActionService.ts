/* global Word */

import type { DocumentAction, DocumentActionResult } from "../types/actions";

export async function replaceCurrentSelection(
  originalText: string,
  newText: string
): Promise<DocumentActionResult> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load("text");

    await context.sync();

    if (selection.text !== originalText) {
      return {
        success: false,
        message:
          "Текущий выделенный текст не совпадает с исходным текстом правки. " +
          "Снова выделите исходный фрагмент и примените правку.",
      };
    }

    selection.insertText(newText, Word.InsertLocation.replace);

    await context.sync();

    return {
      success: true,
      message: "Выделенный текст успешно заменен.",
    };
  });
}

export async function applyDocumentAction(action: DocumentAction): Promise<DocumentActionResult> {
  if (action.type === "replace_selection") {
    return replaceCurrentSelection(action.originalText, action.proposedText);
  }

  return {
    success: false,
    message: "Неподдерживаемое действие с документом.",
  };
}
