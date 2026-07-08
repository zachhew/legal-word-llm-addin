export type DocumentContextMode = "auto" | "full_document" | "selection" | "smart_context";

export type WordDocumentSnapshot = {
  mode: DocumentContextMode;
  text: string;
  capturedAt: string;
  characterCount: number;
};
