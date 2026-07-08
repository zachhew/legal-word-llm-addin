import type { LlmProviderName } from "../types/provider";

export type AppConfig = {
  backendBaseUrl: string;
  backendDisplayUrl: string;
  defaultProvider: LlmProviderName;
  defaultModel: string;
  recommendedOpenRouterModel: string;
  openRouterBaseUrl: string;
};

export const appConfig: AppConfig = {
  backendBaseUrl: "/backend",
  backendDisplayUrl: "http://127.0.0.1:8000",
  defaultProvider: "openrouter",
  defaultModel: "qwen/qwen3.5-flash-02-23",
  recommendedOpenRouterModel: "qwen/qwen3-235b-a22b-thinking-2507",
  openRouterBaseUrl: "https://openrouter.ai/api/v1",
};
