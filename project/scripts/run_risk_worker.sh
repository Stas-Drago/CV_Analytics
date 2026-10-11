#!/usr/bin/env bash
# Run the host-only DangerMLP worker against local Compose PostgreSQL.
# The database password is read into this process only and is never logged.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

task_pg_password="$(awk -F= '$1=="POSTGRES_PASSWORD" {print substr($0, index($0, "=")+1); exit}' .env)"
if [[ -z "$task_pg_password" ]]; then
  echo "POSTGRES_PASSWORD is missing from .env" >&2
  exit 2
fi

exec env \
  SETTINGS_ENV_FILE=.env.host \
  DATABASE_URL="postgresql+psycopg://surveillance:${task_pg_password}@localhost:5432/surveillance" \
  .venv/bin/python -m surveillance.workers risk
