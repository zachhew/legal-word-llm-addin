# Legal Word LLM Add-in

Microsoft Word Office Add-in for legal document workflows.

Repository layout:

```text
backend/   FastAPI API, mock legal service, and LLM provider layer
frontend/  Word task pane add-in built with React, TypeScript, and Office.js
```

The backend supports `mock`, `openrouter`, and `openai_compatible` providers. API keys are
sent only with a request and are not stored by the backend. The project does not use
LangChain, LangGraph, a database, vector DB, embeddings, or auth yet.

## Backend

```bash
cd backend
deactivate 2>/dev/null || true
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

If the virtual environment does not exist yet:

```bash
cd backend
python3 -m venv --prompt backend .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Frontend

Install trusted Office localhost certificates once if they are not installed yet:

```bash
cd frontend
npx office-addin-dev-certs install
```

```bash
cd frontend
npm run dev
```

The task pane frontend uses Vite + React + TypeScript and runs at
`https://localhost:3000/taskpane.html`. Office.js is loaded from the official Microsoft CDN.
During local development it calls the backend through the Vite proxy path `/backend`, forwarded to
`http://127.0.0.1:8000`.

Sideload the Word add-in from a second terminal:

```bash
cd frontend
npm run sideload
```

Stop the sideloaded add-in/debugging session:

```bash
cd frontend
npm run stop
```

If backend calls fail after config changes, restart `npm run dev` so the Vite dev server reloads
`vite.config.ts`.

Optional frontend dev-server variable:

- `BACKEND_PROXY_TARGET`, default `http://127.0.0.1:8000`.

## Configuration

The project does not require storing LLM API keys in environment variables. Users provide API
keys directly in the add-in UI. The backend uses the key only for the current request and does
not persist it.

Backend configuration:

```bash
cp backend/.env.example backend/.env
```

Customize `backend/.env` only if needed: CORS origins, context limits, provider base URLs,
request timeout, and default model. Do not put API keys into `backend/.env`.

Frontend configuration uses Vite with the official Office Add-in sideload/debugging tooling.
Frontend defaults are centralized in:

```text
frontend/src/taskpane/config/appConfig.ts
```

This file contains backend base URL, default provider, default model, and recommended OpenRouter
model. It must not contain API keys.

## Manual Test Flow

1. Start backend on `http://127.0.0.1:8000`.
2. Start frontend with `npm run dev`.
3. Sideload the add-in with `npm run sideload`.
4. In Word, choose provider `OpenRouter`, enter API key and model such as `qwen/qwen3.5-flash-02-23`.
5. Select a legal clause, click `Прочитать выделение`, then run `Проверить риски` or `Переписать пункт`.
6. Review the suggested action.
7. Click `Отклонить правку` to leave Word unchanged, or keep the original fragment selected and click `Применить правку`.

## Checks

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

```bash
cd frontend
npm run lint
npm run build
npx tsc --noEmit
npm run validate
```
