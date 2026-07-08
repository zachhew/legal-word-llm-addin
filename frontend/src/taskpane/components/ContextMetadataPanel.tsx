import * as React from "react";
import type { ContextMetadata } from "../types/backend";

type ContextMetadataPanelProps = {
  metadata: ContextMetadata | null | undefined;
};

export function ContextMetadataPanel({ metadata }: ContextMetadataPanelProps) {
  if (!metadata) {
    return null;
  }

  return (
    <section className="section compact-section" aria-labelledby="context-used-title">
      <h2 id="context-used-title">Использованный контекст</h2>
      <dl className="context-status">
        <div>
          <dt>Стратегия</dt>
          <dd>{metadata.strategy}</dd>
        </div>
        <div>
          <dt>Фрагменты</dt>
          <dd>{metadata.chunksUsed}</dd>
        </div>
        <div>
          <dt>Факты</dt>
          <dd>{metadata.factsUsed}</dd>
        </div>
        <div>
          <dt>Raw-сигналы</dt>
          <dd>{metadata.rawSignalsUsed}</dd>
        </div>
        <div>
          <dt>Конфликты</dt>
          <dd>{metadata.conflictCandidatesUsed}</dd>
        </div>
        {metadata.extractionStrategy ? (
          <div>
            <dt>Извлечение</dt>
            <dd>{metadata.extractionStrategy}</dd>
          </div>
        ) : null}
        <div>
          <dt>Символы контекста</dt>
          <dd>{metadata.totalContextCharacters}</dd>
        </div>
      </dl>
    </section>
  );
}
