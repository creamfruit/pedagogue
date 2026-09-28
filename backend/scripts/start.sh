#!/bin/sh
set -e
if [ "${RUN_RELEASE_ON_START:-false}" = "true" ]; then
  scripts/release.sh
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips "*"
