# Frontend Configuration

This project currently uses the official Office Add-in webpack tooling, not Vite.

Runtime frontend defaults are centralized in `appConfig.ts`:

- backend base URL used by the task pane;
- default provider;
- default model;
- recommended OpenRouter model.

LLM API keys are never stored in this config. Users enter API keys in the add-in UI, and the
backend receives them only for the current request.
