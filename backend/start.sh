#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating backend virtual environment..."
  python3 -m venv --prompt backend .venv
fi

if ! .venv/bin/python -c "import fastapi, uvicorn, pydantic, httpx" >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  .venv/bin/python -m pip install -e ".[dev]"
fi

exec .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8000}"
