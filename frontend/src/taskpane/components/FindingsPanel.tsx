import * as React from "react";
import type { ContextMetadata, Finding } from "../types/backend";

type FindingsPanelProps = {
  findings: Finding[];
  contextMetadata?: ContextMetadata | null;
};

function severityLabel(severity?: string | null): string {
  if (severity === "high") {
    return "Высокий";
  }
  if (severity === "medium") {
    return "Средний";
  }
  if (severity === "low") {
    return "Низкий";
  }
  return "Без оценки";
}

function formatEvidenceLabel(chunkId: string, contextMetadata?: ContextMetadata | null): string {
  const sourceChunk = contextMetadata?.sourceChunks.find((chunk) => chunk.chunkId === chunkId);

  if (!sourceChunk) {
    return chunkId;
  }

  const title = sourceChunk.title || sourceChunk.sectionPath[sourceChunk.sectionPath.length - 1];
  if (!title) {
    return chunkId;
  }

  return `${title} (${chunkId})`;
}

export function FindingsPanel({ findings, contextMetadata }: FindingsPanelProps) {
  if (!findings.length) {
    return null;
  }

  return (
    <section className="section compact-section" aria-labelledby="findings-title">
      <h2 id="findings-title">Выводы</h2>
      <div className="findings-list">
        {findings.map((finding, index) => (
          <article className="finding-card" key={`${finding.type}-${finding.title}-${index}`}>
            <div className="finding-header">
              <h3>{finding.title}</h3>
              <span className={`severity-badge severity-${finding.severity || "none"}`}>
                {severityLabel(finding.severity)}
              </span>
            </div>
            <p>{finding.explanation}</p>
            {finding.evidenceChunkIds.length ? (
              <div className="finding-sources">
                <span>Найдено в:</span>
                {finding.evidenceChunkIds.map((chunkId) => (
                  <span className="source-pill" key={chunkId}>
                    {formatEvidenceLabel(chunkId, contextMetadata)}
                  </span>
                ))}
              </div>
            ) : null}
            {finding.recommendation ? <p>{finding.recommendation}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
