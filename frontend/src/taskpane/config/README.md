# Конфигурация frontend

Frontend использует Vite для task pane и официальный Office Add-in tooling для проверки manifest
и sideload в Word.

Runtime defaults собраны в `appConfig.ts`:

- base URL backend proxy;
- provider по умолчанию;
- model по умолчанию;
- recommended OpenRouter model;
- OpenRouter base URL.

LLM API keys здесь не хранятся. Пользователь вводит API key в интерфейсе надстройки, backend
получает его только в рамках текущего запроса.
