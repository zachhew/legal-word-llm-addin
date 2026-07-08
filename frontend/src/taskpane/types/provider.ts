import { appConfig } from "../config/appConfig";

export type LlmProviderName = "mock" | "openrouter" | "openai_compatible";

export type ProviderSettings = {
  provider: LlmProviderName;
  model: string;
  baseUrl?: string;
  apiKey?: string;
};

export const DEFAULT_PROVIDER_SETTINGS: ProviderSettings = {
  provider: appConfig.defaultProvider,
  model: appConfig.defaultModel,
  baseUrl: appConfig.defaultProvider === "openrouter" ? appConfig.openRouterBaseUrl : "",
  apiKey: "",
};
