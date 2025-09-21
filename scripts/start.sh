#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-true}"

if command -v uvicorn >/dev/null 2>&1; then
  CMD=(uvicorn app.main:app)
else
  CMD=(python -m uvicorn app.main:app)
fi

if [[ "${RELOAD}" == "true" ]]; then
  CMD+=(--reload)
fi

CMD+=(--host "${HOST}" --port "${PORT}")

exec "${CMD[@]}"


