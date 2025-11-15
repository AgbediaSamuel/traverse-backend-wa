#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
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
CMD+=(--timeout-keep-alive 600)  # 10 minutes keep-alive timeout
CMD+=(--timeout-graceful-shutdown 30)  # 30 seconds graceful shutdown

exec "${CMD[@]}"


