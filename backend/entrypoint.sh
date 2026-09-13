#!/bin/sh
set -e
mkdir -p /app/data
WORKERS=${UVICORN_WORKERS:-1}
echo "[entrypoint] starting AgentWorks backend on :${PORT:-8700} (workers=${WORKERS})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8700}" \
  --workers "${WORKERS}" --log-level "${LOG_LEVEL:-info}" --proxy-headers --forwarded-allow-ips "*"
