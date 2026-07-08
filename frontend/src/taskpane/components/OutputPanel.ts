import * as React from "react";

const e = React.createElement;

type OutputPanelProps = {
  output: string;
  error: string | null;
  isLoading?: boolean;
};

export function OutputPanel({ output, error, isLoading = false }: OutputPanelProps) {
  return e(
    "section",
    { className: "section result-section", "aria-labelledby": "output-title" },
    e("h2", { id: "output-title" }, "Результат анализа"),
    isLoading ? e("p", { className: "loading-message" }, "Выполняется запрос...") : null,
    error ? e("p", { className: "error-message" }, error) : null,
    e("pre", { className: "result-output" }, output)
  );
}
