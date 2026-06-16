#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_ROOT="${VIEWTUBE_LOCAL_UCLOUD_ROOT:-$APP_DIR/.local-ucloud}"
DATA_DIR="${VIEWTUBE_DATA_DIR:-$LOCAL_ROOT/data}"
LOG_DIR="${VIEWTUBE_LOG_DIR:-$LOCAL_ROOT/logs}"
SOURCE_DB_PATH="${VIEWTUBE_LOCAL_SOURCE_DB_PATH:-$APP_DIR/backend/app.db}"
CONTENT_DB_PATH="${VIEWTUBE_CONTENT_DB_PATH:-$DATA_DIR/viewtube_content.sqlite}"
BEHAVIOR_DB_PATH="${VIEWTUBE_BEHAVIOR_DB_PATH:-$DATA_DIR/viewtube_behavior.sqlite}"
PY_DEPS_DIR="$(python3 "$APP_DIR/scripts/python_deps_path.py" 2>/dev/null || printf '%s/.python_deps' "$APP_DIR")"

prepare_split() {
  local force_flag=()
  if [[ "${1:-}" == "--force" ]]; then
    force_flag=(--force)
  fi
  mkdir -p "$DATA_DIR" "$LOG_DIR"
  python3 "$APP_DIR/scripts/split_sqlite_databases.py" \
    --source "$SOURCE_DB_PATH" \
    --content-db "$CONTENT_DB_PATH" \
    --behavior-db "$BEHAVIOR_DB_PATH" \
    "${force_flag[@]}"
}

export_local_ucloud_env() {
  export CONTENT_DATABASE_URL="sqlite:///$CONTENT_DB_PATH"
  export BEHAVIOR_DATABASE_URL="sqlite:///$BEHAVIOR_DB_PATH"
  export DATABASE_URL="$CONTENT_DATABASE_URL"
  export PYTHONPATH="$PY_DEPS_DIR:$APP_DIR/.python_deps:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
  export NEXT_TELEMETRY_DISABLED=1
}

run_with_env() {
  export_local_ucloud_env
  "$@"
}

usage() {
  cat <<EOF
Usage: scripts/local_ucloud_mode.sh <command>

Commands:
  prepare [--force]   Split backend/app.db into local content + behavior DBs
  env                 Print the local UCloud-like database environment variables
  build               Run npm build against split local content/behavior DBs
  test:backend        Run backend tests against split local content/behavior DBs
  verify              Verify that logging writes to behavior DB only
  run <cmd...>        Run any command with UCloud-like split DB environment

Local paths:
  root:      $LOCAL_ROOT
  source DB: $SOURCE_DB_PATH
  content:   $CONTENT_DB_PATH
  behavior:  $BEHAVIOR_DB_PATH
EOF
}

main() {
  local command="${1:-}"
  case "$command" in
    prepare)
      shift || true
      prepare_split "${1:-}"
      ;;
    env)
      prepare_split
      export_local_ucloud_env
      printf 'CONTENT_DATABASE_URL=%s\n' "$CONTENT_DATABASE_URL"
      printf 'BEHAVIOR_DATABASE_URL=%s\n' "$BEHAVIOR_DATABASE_URL"
      printf 'DATABASE_URL=%s\n' "$DATABASE_URL"
      ;;
    build)
      prepare_split
      run_with_env npm run build
      ;;
    test:backend)
      prepare_split
      run_with_env npm run test:backend
      ;;
    verify)
      prepare_split --force
      run_with_env python3 "$APP_DIR/scripts/verify_local_ucloud_mode.py"
      ;;
    run)
      shift || true
      if [[ "$#" -eq 0 ]]; then
        usage
        exit 1
      fi
      prepare_split
      run_with_env "$@"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
