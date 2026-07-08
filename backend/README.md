# Backend юридического Word Add-in

FastAPI backend для Microsoft Word Add-in, который анализирует юридические документы и возвращает
структурированные ответы для frontend.

Поддерживаемые провайдеры:

- `mock`
- `openrouter`
- `openai_compatible`

API key принимается только в body конкретного запроса. Backend не хранит API key и не логирует его.

Word task pane не обращается к backend напрямую. В локальной разработке frontend использует Vite
proxy `/backend/*`, который проксирует запросы на `http://127.0.0.1:8000/*`. Это защищает от
HTTPS-to-HTTP mixed-content проблем в Office WebView.

## Установка

```bash
cd backend
python3 -m venv --prompt backend .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Запуск

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Без активации окружения:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Fallback-скрипт:

```bash
cd backend
./start.sh
```

После изменения `frontend/vite.config.ts` перезапустите `npm run dev` в `frontend`, чтобы Vite
proxy перечитал настройки.

## Конфигурация

Backend читает optional settings из `backend/.env`.

```bash
cp backend/.env.example backend/.env
```

В `.env` можно менять:

- `CORS_ORIGINS`
- `MAX_DOCUMENT_TEXT_CHARS`
- `MAX_SELECTION_TEXT_CHARS`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_TITLE`
- provider base URLs
- LLM timeout
- context/chunk limits

Не добавляйте OpenRouter/OpenAI API keys в `.env`. Пользователь вводит ключ в UI, backend
использует его только в текущем запросе.

## Endpoints

- `GET /health`
- `POST /api/legal/run`
- `POST /api/legal/jobs`
- `GET /api/legal/jobs/{job_id}`
- `POST /api/legal/context-debug`
- `POST /api/legal/risk-review`
- `POST /api/legal/rewrite-clause`

## Provider Settings

`POST /api/legal/run` принимает optional provider settings:

```json
{
  "provider": "openrouter",
  "model": "qwen/qwen3.5-flash-02-23",
  "base_url": "https://openrouter.ai/api/v1",
  "api_key": "request-time-key"
}
```

Правила:

- `mock` не требует API key, model или base URL;
- `openrouter` требует `api_key` и `model`, base URL по умолчанию `https://openrouter.ai/api/v1`;
- `openai_compatible` требует `api_key`, `model` и `base_url`.

Provider должен вернуть JSON object. Backend normalizes response, валидирует suggested actions и
не возвращает невалидные правки во frontend.

## Context Strategy

Поддерживаются режимы:

- `auto`
- `selection`
- `full_document`
- `smart_context`

`auto` выбирает стратегию по сценарию:

- clause rewrite использует выделенный пункт;
- risk review использует выделенный пункт плюс связанные секции;
- inconsistency check использует section-aware chunks, raw signals, LLM fact extraction и conflict candidates;
- chat использует выделение, полный документ или smart context.

## Почему нет hardcoded legal parser

Backend не реализует самодельный regex-парсер русского юридического языка.

Regex используется только для технических сигналов:

- сроки;
- проценты;
- суммы;
- даты;
- ссылки на пункты.

Семантические юридические факты извлекаются LLM через отдельный structured JSON prompt. Затем
backend детерминированно группирует факты и ищет conflict candidates.

## Long-Running Jobs

Full-document inconsistency analysis может идти дольше, чем удобно держать один HTTP request в
Office WebView. Поэтому frontend использует job endpoints:

1. `POST /api/legal/jobs` создает job и возвращает `job_id`.
2. `GET /api/legal/jobs/{job_id}` опрашивает статус.
3. При успехе возвращается тот же `LegalResponse`, что и в `/api/legal/run`.

Jobs сейчас in-memory и рассчитаны на локальный single-process backend. API keys не сохраняются
в job records.

## Примеры

Health:

```bash
curl http://127.0.0.1:8000/health
```

Risk review с mock provider:

```bash
curl -X POST http://127.0.0.1:8000/api/legal/run \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "risk_review",
    "message": "Проверь риски.",
    "document_context": {
      "mode": "selection",
      "text": "Ответственность Исполнителя не ограничена.",
      "character_count": 41
    },
    "provider": {
      "provider": "mock"
    }
  }'
```

## Тесты

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```
