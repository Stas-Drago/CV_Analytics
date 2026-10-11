#!/usr/bin/env sh
# Run only on the macOS host that physically owns the USB camera.
set -eu

cd "$(dirname "$0")/.."
set -a
[ -f .env ] && . ./.env
[ -f .env.host ] && . ./.env.host
set +a

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}"
export DATABASE_URL="postgresql+psycopg://surveillance:${POSTGRES_PASSWORD}@localhost:5432/surveillance"
export REDIS_URL="redis://localhost:6379/0"
export SETTINGS_ENV_FILE=".env.host"

exec .venv/bin/python -m surveillance.camera
