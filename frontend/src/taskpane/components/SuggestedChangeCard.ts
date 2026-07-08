import * as React from "react";
import type { DocumentAction } from "../types/actions";

const e = React.createElement;

type SuggestedChangeCardProps = {
  action: DocumentAction;
  onApply: () => void;
  onReject: () => void;
  isLoading: boolean;
};

export function SuggestedChangeCard({
  action,
  onApply,
  onReject,
  isLoading,
}: SuggestedChangeCardProps) {
  const shouldShowRationale =
    action.rationaleSource !== "fallback" && Boolean(action.rationale.trim());

  return e(
    "section",
    { className: "section suggested-change", "aria-labelledby": "suggested-change-title" },
    e("h2", { id: "suggested-change-title" }, "Предложенная правка"),
    e("h3", null, action.title),
    e(
      "div",
      { className: "change-grid" },
      e(
        "div",
        { className: "change-block change-block-old" },
        e("span", null, "Исходный текст"),
        e("pre", null, action.originalText)
      ),
      e(
        "div",
        { className: "change-block change-block-new" },
        e("span", null, "Предлагаемый текст"),
        e("pre", null, action.proposedText)
      )
    ),
    shouldShowRationale
      ? e(
          "div",
          { className: "rationale" },
          e("span", null, "Обоснование"),
          e("p", null, action.rationale)
        )
      : null,
    e(
      "div",
      { className: "button-stack" },
      e("button", { type: "button", onClick: onApply, disabled: isLoading }, "Применить правку"),
      e(
        "button",
        { type: "button", onClick: onReject, disabled: isLoading, className: "secondary-button" },
        "Отклонить правку"
      )
    )
  );
}
