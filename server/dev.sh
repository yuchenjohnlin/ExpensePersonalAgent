#!/usr/bin/env bash
# Developing server/ on the Mac: one PostgreSQL 17 in Docker, its data in the volume
# cojidaily-serverdev-pgdata. The tests make and drop their own database (cojidaily_test);
# `run` uses cojidaily_dev, which survives restarts.
#
#   server/dev.sh test [pytest args]   the tests, on the host with uv
#   server/dev.sh run                  the API on 127.0.0.1:8000 (reloading on edits) and the
#                                      worker beside it, on cojidaily_dev
#   server/dev.sh cli ARGS             python -m cojidaily.cli on cojidaily_dev (createuser NAME)
#                                      (both migrate cojidaily_dev first)
#   server/dev.sh psql [args]          psql in that database server
#   server/dev.sh stop                 remove the container (the volume stays)
#
# `run` and `cli` read server/.env when it exists (VLLM_*, COJI_*; git-ignored). Photos go to
# server/media/. Only 127.0.0.1 ports, its own names: nothing here touches the other stacks.
set -euo pipefail
cd "$(dirname "$0")"

DB=cojidaily-serverdev-pg
PORT=5434
PASSWORD=serverdev
SERVER_URL="postgresql+psycopg://postgres:$PASSWORD@127.0.0.1:$PORT"

pg_up() {
  if ! docker container inspect $DB >/dev/null 2>&1; then
    docker run -d --rm --name $DB -p 127.0.0.1:$PORT:5432 -v cojidaily-serverdev-pgdata:/var/lib/postgresql/data \
      -e POSTGRES_PASSWORD=$PASSWORD postgres:17 >/dev/null
  fi
  # Over TCP: the image's first-start server listens on the socket only, so this waits for the real one.
  until docker exec $DB pg_isready -q -h 127.0.0.1 -U postgres; do sleep 1; done
}

dev_env() {
  pg_up
  if [ -z "$(docker exec $DB psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'cojidaily_dev'")" ]; then
    docker exec $DB createdb -U postgres cojidaily_dev
  fi
  if [ -f .env ]; then
    set -a
    . ./.env
    set +a
  fi
  export COJI_DATABASE_URL="${COJI_DATABASE_URL:-$SERVER_URL/cojidaily_dev}"
  export COJI_SECRET_KEY="${COJI_SECRET_KEY:-dev only, not secret}"
  export COJI_BLOB_ROOT="${COJI_BLOB_ROOT:-$PWD/media}"
  uv run alembic upgrade head 2>&1 | grep -v '^INFO' || true
}

case "${1:-}" in
  test)
    pg_up
    shift
    COJI_TEST_DATABASE_URL="$SERVER_URL/postgres" exec uv run pytest "$@"
    ;;
  run)
    dev_env
    uv run python -m cojidaily.worker &
    worker=$!
    trap 'kill $worker 2>/dev/null' EXIT
    uv run uvicorn cojidaily.main:create_app --factory --reload --reload-dir src --host 127.0.0.1 --port 8000
    ;;
  cli)
    dev_env
    shift
    exec uv run python -m cojidaily.cli "$@"
    ;;
  psql)
    pg_up
    shift
    exec docker exec -it $DB psql -U postgres "$@"
    ;;
  stop)
    docker rm -f $DB >/dev/null 2>&1 || true
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 2
    ;;
esac
