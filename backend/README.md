# Legal Word LLM Backend

FastAPI backend for the Microsoft Word legal assistant add-in.

Supported providers:

- `mock`
- `openrouter`
- `openai_compatible`

API keys are accepted only in request bodies for request-time provider calls. The backend
does not store API keys and does not log them.

The Word task pane does not call this backend directly from `https://localhost:3000`.
In local development, webpack proxies frontend requests from `/backend/*` to
`http://127.0.0.1:8000/*` to avoid HTTPS-to-HTTP mixed-content failures in Office WebView.

## Install

```bash
cd backend
python3 -m venv --prompt backend .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Run

```bash
cd backend
deactivate 2>/dev/null || true
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

After activation your prompt should start with `(backend)`. If it still starts with `(.venv)`,
you are probably using the repository-level virtual environment instead of `backend/.venv`.

No-activation fallback:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Self-setup fallback:

```bash
cd backend
./start.sh
```

After changing `frontend/webpack.config.js`, restart `npm start` in `frontend/`; otherwise
the task pane may still use the old dev-server proxy configuration.

Optional environment variables:

- `CORS_ORIGINS` comma-separated allowed origins.
- `MAX_DOCUMENT_TEXT_CHARS` maximum `text`/`full_text` request size, default `200000`.
- `MAX_SELECTION_TEXT_CHARS` maximum `selection_text` request size, default `30000`.
- `OPENROUTER_HTTP_REFERER` OpenRouter referer header, default `http://localhost:3000`.
- `OPENROUTER_APP_TITLE` OpenRouter title header, default `Legal Word LLM Add-in`.

## Configuration

The backend reads optional settings from `backend/.env`. Start from the example file:

```bash
cp backend/.env.example backend/.env
```

You can configure app metadata, CORS origins, provider base URLs, LLM request timeout, and
context/chunk limits there. Do not put OpenRouter/OpenAI API keys into `.env`; users enter API
keys in the add-in UI and the backend uses them only for the current request.

## Test

```bash
cd backend
.venv/bin/python -m pytest
```

## Endpoints

- `GET /health`
- `POST /api/legal/run`
- `POST /api/legal/jobs`
- `GET /api/legal/jobs/{job_id}`
- `POST /api/legal/context-debug`
- `POST /api/legal/risk-review`
- `POST /api/legal/rewrite-clause`

## Provider Settings

`POST /api/legal/run` accepts optional provider settings:

```json
{
  "provider": "openrouter",
  "model": "qwen/qwen3.5-flash-02-23",
  "base_url": "https://openrouter.ai/api/v1",
  "api_key": "request-time-key"
}
```

Validation rules:

- `mock` does not require API key, model, or base URL.
- `openrouter` requires `api_key` and `model`; base URL defaults to `https://openrouter.ai/api/v1`.
- `openai_compatible` requires `api_key`, `model`, and `base_url`.

LLM providers must return a JSON object with `answer`, `suggested_actions`, and `warnings`.
Invalid suggested actions are not returned to the frontend; they are converted to warnings.

## Long Document Handling / Context Strategy

The add-in supports four document context modes:

- `auto`
- `selection`
- `full_document`
- `smart_context`

`auto` is scenario-aware:

- clause rewrite uses the selected clause and may include a small number of related chunks;
- risk review uses the selected clause plus related legal sections when selection and full text
  are available, otherwise it falls back to smart legal retrieval;
- inconsistency check uses section-aware chunks, low-level raw signals, LLM-based structured
  legal fact extraction, and deterministic conflict candidates so the final analysis reviews
  likely contradictions instead of searching the whole document blindly;
- chat uses the selected text, full document, or smart context depending on the available input
  and context size.

The current implementation intentionally avoids vector DBs and embeddings. Context selection is
deterministic and local: section parsing, low-level signal extraction, conflict grouping, and
explainable lexical retrieval. `RetrievalService` can be replaced with embeddings/vector search
later without changing the Word controlled editing flow.

## Why No Hardcoded Legal Parser

The backend intentionally avoids hardcoded Russian legal regex parsers. Regex is used only for
low-level raw signals such as dates, percentages, periods, money amounts, and clause references.
It does not decide that a period is a payment term, an acceptance term, or a termination notice.

Semantic legal fact extraction is delegated to the configured LLM through a separate structured
JSON extraction prompt. The backend then validates, groups, and compares the extracted facts
deterministically. This keeps the system more flexible across different legal drafting styles.

In `mock` mode, the backend may create lightweight demo facts from raw signals and section titles
only so context metadata remains useful without an API key. Real semantic extraction requires a
real provider such as OpenRouter or an OpenAI-compatible endpoint.

Responses may include `findings` and `context_metadata`. The frontend displays both, while
`suggested_actions` still go through preview and Apply/Reject. The backend never edits Word.

`POST /api/legal/context-debug` returns the built context without calling an LLM provider. Use it
to inspect selected chunks, extracted facts, conflict candidates, and context metadata.

## Long-Running Analysis Jobs

Full-document inconsistency analysis can take longer than Office WebView or the webpack dev proxy
comfortably keeps a single HTTP request open, especially with slower OpenRouter models. For that
case the frontend uses job endpoints:

1. `POST /api/legal/jobs` creates a background legal analysis job and returns `job_id`.
2. `GET /api/legal/jobs/{job_id}` polls status until `succeeded` or `failed`.
3. A successful job returns the same `LegalResponse` shape as `POST /api/legal/run`.

Jobs are currently in-memory and intended for the local single-process backend. They do not store
API keys in job records; provider settings live only in the running background task.

## Health Example

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "legal-word-llm-backend"
}
```

## Legal Scenario Example

```bash
curl -X POST http://127.0.0.1:8000/api/legal/run \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "risk_review",
    "message": "Проверь риски.",
    "document_context": {
      "mode": "selection",
      "text": "Ответственность Исполнителя не ограничена.",
      "character_count": 41,
      "captured_at": "2026-07-08T00:00:00Z"
    },
    "provider": {
      "provider": "mock"
    }
  }'
```

The response contains a Russian-language answer and, when appropriate, a `replace_selection`
suggested action. The backend never edits Word directly; frontend Apply/Reject controls the
actual Word edit.
