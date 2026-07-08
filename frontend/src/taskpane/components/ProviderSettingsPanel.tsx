import * as React from "react";
import { appConfig } from "../config/appConfig";
import type { LlmProviderName, ProviderSettings } from "../types/provider";

type ProviderSettingsPanelProps = {
  settings: ProviderSettings;
  onChange: (settings: ProviderSettings) => void;
  isLoading: boolean;
};

function providerDefaults(provider: LlmProviderName, current: ProviderSettings): ProviderSettings {
  if (provider === "openrouter") {
    return {
      provider,
      model: current.model || appConfig.recommendedOpenRouterModel,
      baseUrl: current.baseUrl || appConfig.openRouterBaseUrl,
      apiKey: current.apiKey || "",
    };
  }

  return {
    provider,
    model: current.model,
    baseUrl: current.baseUrl || "",
    apiKey: current.apiKey || "",
  };
}

export function ProviderSettingsPanel({
  settings,
  onChange,
  isLoading,
}: ProviderSettingsPanelProps) {
  const isOpenRouter = settings.provider === "openrouter";

  function updateSettings(patch: Partial<ProviderSettings>): void {
    onChange({
      ...settings,
      ...patch,
    });
  }

  return (
    <details className="section details-section">
      <summary id="provider-settings-title">Настройки модели</summary>

      <div className="form-grid">
        <label htmlFor="provider-name">Провайдер</label>
        <select
          id="provider-name"
          value={settings.provider}
          disabled={isLoading}
          onChange={(event: React.ChangeEvent<HTMLSelectElement>) =>
            onChange(providerDefaults(event.target.value as LlmProviderName, settings))
          }
        >
          <option value="openrouter">OpenRouter</option>
          <option value="openai_compatible">OpenAI-compatible</option>
        </select>

        <label htmlFor="provider-model">Модель</label>
        <input
          id="provider-model"
          type="text"
          value={settings.model}
          disabled={isLoading}
          placeholder={isOpenRouter ? appConfig.recommendedOpenRouterModel : "model-name"}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
            updateSettings({ model: event.target.value })
          }
        />

        <label htmlFor="provider-base-url">Base URL</label>
        <input
          id="provider-base-url"
          type="text"
          value={settings.baseUrl || ""}
          disabled={isLoading}
          placeholder={
            isOpenRouter ? appConfig.openRouterBaseUrl : "https://your-provider.example/v1"
          }
          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
            updateSettings({ baseUrl: event.target.value })
          }
        />

        <label htmlFor="provider-api-key">API key</label>
        <input
          id="provider-api-key"
          type="password"
          value={settings.apiKey || ""}
          disabled={isLoading}
          placeholder="Введите ключ API"
          onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
            updateSettings({ apiKey: event.target.value })
          }
        />
      </div>

      <p className="help-text">
        OpenRouter использует OpenAI-compatible Chat Completions API. API key отправляется
        только вместе с запросом и не сохраняется backend.
      </p>
    </details>
  );
}
