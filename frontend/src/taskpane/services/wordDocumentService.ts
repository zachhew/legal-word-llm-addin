/* global Word */

import type { DocumentContextMode, WordDocumentSnapshot } from "../types/document";

function createSnapshot(mode: DocumentContextMode, text: string): WordDocumentSnapshot {
  return {
    mode,
    text,
    capturedAt: new Date().toISOString(),
    characterCount: text.length,
  };
}

export async function readFullDocument(): Promise<WordDocumentSnapshot> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load("text");

    await context.sync();

    return createSnapshot("full_document", body.text || "");
  });
}

export async function readSelection(): Promise<WordDocumentSnapshot> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load("text");

    await context.sync();

    return createSnapshot("selection", selection.text || "");
  });
}
