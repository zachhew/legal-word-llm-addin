export type DocumentActionType = "replace_selection";

export type ReplaceSelectionAction = {
  type: "replace_selection";
  title: string;
  originalText: string;
  proposedText: string;
  rationale: string;
  rationaleSource?: "llm" | "fallback";
  createdAt: string;
};

export type DocumentAction = ReplaceSelectionAction;

export type DocumentActionResult = {
  success: boolean;
  message: string;
};
