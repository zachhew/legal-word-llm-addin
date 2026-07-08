# Frontend Configuration

This project uses Vite for the task pane frontend and the official Office Add-in tooling for
manifest validation and Word sideloading.

Runtime frontend defaults are centralized in `appConfig.ts`:

- backend base URL used by the task pane;
- default provider;
- default model;
- recommended OpenRouter model.

LLM API keys are never stored in this config. Users enter API keys in the add-in UI, and the
backend receives them only for the current request.
