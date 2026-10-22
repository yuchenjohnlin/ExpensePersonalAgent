#!/usr/bin/env bash
# Running the rebuilt app on the PC (deploy/README.md). Works from the repo checkout; each
# environment is the compose project coji-<env>.
#
#   deploy/deploy.sh init ENV [FILE]        write deploy/secrets/ENV.env: a new database password and
#                                           session key, VLLM_* copied from FILE (default: the repo's .env)
#   deploy/deploy.sh build                  build both images from the commit checked out, tagged with it
#   deploy/deploy.sh up ENV [TAG]           run ENV on TAG (default: the commit checked out): migrate,
#                                           start, wait until healthy, check that the page and API answer
#   deploy/deploy.sh promote                back up prod, then run it on the tag test runs now
#   deploy/deploy.sh status                 the tag each environment runs, and the containers
#   deploy/deploy.sh cli ENV ARGS...        python -m cojidaily.cli in ENV (createuser NAME)
#   deploy/deploy.sh logs ENV [SERVICE]     follow the logs
#   deploy/deploy.sh down ENV               stop ENV and remove its containers; its volumes stay
#   deploy/deploy.sh reset test [TAG]       down, delete test's database and photos, up again
#   deploy/deploy.sh obs up|down            the observability stack (Grafana on :3000)
#   deploy/deploy.sh backup ENV             database dump and photos into ~/cojidaily-backups/ENV/<time>/
#   deploy/deploy.sh restore-check ENV DIR  restore DIR into a scratch database beside ENV's and compare
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUPS=${COJI_BACKUPS:-$HOME/cojidaily-backups}
KEEP=${COJI_BACKUP_KEEP:-14}

usage() { sed -n '2,20p' "$0"; exit 2; }
fail() { echo "$*" >&2; exit 1; }

env_name() {
  case "${1:-}" in
    test|prod) echo "$1" ;;
    *) fail "ENV is test or prod" ;;
  esac
}

head_tag() { git rev-parse --short=12 HEAD; }

# The tag ENV's API container runs; nothing when it is not there.
running_tag() {
  docker inspect --format '{{.Config.Image}}' "coji-$1-api-1" 2>/dev/null | sed -n 's/^cojidaily-server://p' || true
}

port() { sed -n 's/^WEB_PORT=//p' "deploy/$1.env"; }

ensure_obs_network() {
  docker network inspect coji-obs >/dev/null 2>&1 || docker network create coji-obs >/dev/null
}

compose() {  # compose ENV ARGS...
  local env=$1 tag=${TAG:-}
  shift
  [ -f "deploy/secrets/$env.env" ] || fail "no deploy/secrets/$env.env: run deploy/deploy.sh init $env"
  # Every command reads the whole file, which names an image tag; for logs or exec any will do.
  [ -n "$tag" ] || tag=$(running_tag "$env")
  [ -n "$tag" ] || tag=$(head_tag)
  TAG=$tag docker compose -p "coji-$env" -f deploy/compose.yaml --env-file "deploy/$env.env" \
    --env-file "deploy/secrets/$env.env" "$@"
}

init() {
  local env source file key
  env=$(env_name "${1:-}")
  source=${2:-.env}
  file=deploy/secrets/$env.env
  [ ! -e "$file" ] || fail "$file exists. The database keeps the password it was created with: delete the file only together with the volume."
  mkdir -p deploy/secrets
  (
    umask 077
    {
      echo "# Secrets of the $env environment (deploy/README.md); not in git."
      echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
      echo "COJI_SECRET_KEY=$(openssl rand -hex 32)"
      for key in VLLM_BASE_URL VLLM_MODEL VLLM_API_KEY VLLM_TIMEOUT_SECONDS; do
        grep -m1 "^$key=" "$source" 2>/dev/null || echo "$key="
      done
    } > "$file"
  )
  echo "wrote $file"
  grep -q '^VLLM_BASE_URL=.' "$file" || echo "VLLM_BASE_URL is empty: fill it in before deploy/deploy.sh up $env" >&2
}

build() {
  local tag revision
  [ -z "$(git status --porcelain -- server web)" ] ||
    fail "server/ or web/ has uncommitted changes: an image tagged $(head_tag) would not be that commit"
  tag=$(head_tag)
  revision=$(git rev-parse HEAD)
  docker build --label "org.opencontainers.image.revision=$revision" -t "cojidaily-server:$tag" server
  docker build --label "org.opencontainers.image.revision=$revision" -t "cojidaily-web:$tag" web
  echo "built cojidaily-server:$tag and cojidaily-web:$tag"
}

check() {  # the page and the API answer through nginx, the way the browser reaches them
  local base
  base=http://127.0.0.1:$(port "$1")
  curl -fsS "$base/api/health" >/dev/null || fail "$base/api/health does not answer"
  curl -fsS "$base/" | grep -q 'id="root"' || fail "$base/ is not the app's page"
}

up() {
  local env tag image
  env=$(env_name "${1:-}")
  tag=${2:-$(head_tag)}
  for image in server web; do
    docker image inspect "cojidaily-$image:$tag" >/dev/null 2>&1 ||
      fail "no image cojidaily-$image:$tag: run deploy/deploy.sh build on that commit"
  done
  ensure_obs_network
  TAG=$tag compose "$env" up -d --wait db
  TAG=$tag compose "$env" run --rm -T migrate
  TAG=$tag compose "$env" up -d --wait --remove-orphans
  check "$env"
  echo "$env runs $tag on port $(port "$env")"
}

promote() {
  local tag
  tag=$(running_tag test)
  [ -n "$tag" ] || fail "test is not running: nothing to promote"
  if [ -n "$(running_tag prod)" ]; then
    echo "backing up prod before it changes"
    backup prod
  fi
  up prod "$tag"
}

status() {
  local env tag
  for env in test prod; do
    tag=$(running_tag "$env")
    printf '%-5s %s\n' "$env" "${tag:-(not running)}"
  done
  printf '%-5s %s\n' HEAD "$(head_tag)"
  docker ps --filter 'name=^coji-' --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
}

reset() {
  local tag
  [ "${1:-}" = test ] || fail "only test can be reset"
  tag=${2:-$(running_tag test)}
  tag=${tag:-$(head_tag)}
  compose test down --volumes
  up test "$tag"
}

obs() {
  ensure_obs_network
  case "${1:-}" in
    up) docker compose -f deploy/observability/compose.yaml up -d --wait ;;
    down) docker compose -f deploy/observability/compose.yaml down ;;
    *) usage ;;
  esac
}

backup() {
  local env dir i
  env=$(env_name "${1:-}")
  dir=$BACKUPS/$env/$(date +%Y-%m-%dT%H%M%S)
  mkdir -p "$dir"
  compose "$env" exec -T db pg_dump -U coji -d cojidaily --format=custom > "$dir/db.dump"
  # As this user, so the backup's files are not root's.
  docker run --rm --user "$(id -u):$(id -g)" -v "coji-${env}_blobs:/blobs:ro" -v "$dir:/backup" \
    postgres:17 tar czf /backup/blobs.tgz -C /blobs .
  printf 'tag=%s\ntime=%s\n' "$(running_tag "$env")" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$dir/manifest"
  # Keep the newest $KEEP; the names sort by time.
  local all=("$BACKUPS/$env"/*/)
  for (( i = 0; i < ${#all[@]} - KEEP; i++ )); do rm -rf "${all[$i]}"; done
  echo "$dir"
}

# Exact rows per table, one "table|rows" line each.
COUNTS="SELECT table_name, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I', table_name), false, true, '')))[1]::text
FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"

restore_check() {
  local env dir live restored files_live files_backup
  env=$(env_name "${1:-}")
  dir=${2:-}
  [ -f "$dir/db.dump" ] && [ -f "$dir/blobs.tgz" ] || fail "no backup in '$dir'"
  compose "$env" exec -T db dropdb -U coji --if-exists restore_check
  compose "$env" exec -T db createdb -U coji restore_check
  compose "$env" exec -T db pg_restore -U coji -d restore_check --no-owner < "$dir/db.dump"
  live=$(compose "$env" exec -T db psql -U coji -d cojidaily -tAc "$COUNTS")
  restored=$(compose "$env" exec -T db psql -U coji -d restore_check -tAc "$COUNTS")
  compose "$env" exec -T db dropdb -U coji restore_check
  files_live=$(docker run --rm -v "coji-${env}_blobs:/blobs:ro" postgres:17 find /blobs -type f | wc -l | tr -d ' ')
  files_backup=$(tar tzf "$dir/blobs.tgz" | grep -vc '/$' || true)
  echo "table|live rows|restored rows"
  paste -d'|' <(echo "$live") <(echo "$restored" | cut -d'|' -f2)
  echo "photo files: live $files_live, in the backup $files_backup"
  if [ "$live" = "$restored" ] && [ "$files_live" = "$files_backup" ]; then
    echo "the backup restores to the same rows and files"
  else
    echo "they differ: either $env changed since the backup or the backup is incomplete" >&2
    exit 1
  fi
}

case "${1:-}" in
  init) shift; init "$@" ;;
  build) build ;;
  up) shift; up "$@" ;;
  promote) promote ;;
  status) status ;;
  cli)
    shift
    env=$(env_name "${1:-}")
    shift
    if [ -t 0 ]; then compose "$env" exec api python -m cojidaily.cli "$@"
    else compose "$env" exec -T api python -m cojidaily.cli "$@"; fi
    ;;
  logs)
    shift
    env=$(env_name "${1:-}")
    shift
    compose "$env" logs -f --tail 100 "$@"
    ;;
  down)
    shift
    env=$(env_name "${1:-}")
    compose "$env" down
    ;;
  reset) shift; reset "$@" ;;
  obs) shift; obs "$@" ;;
  backup) shift; backup "$@" ;;
  restore-check) shift; restore_check "$@" ;;
  *) usage ;;
esac
