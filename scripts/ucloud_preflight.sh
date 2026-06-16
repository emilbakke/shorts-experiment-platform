#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSIST_ROOT="${VIEWTUBE_PERSIST_ROOT:-/work/viewtube}"
DATA_DIR="${VIEWTUBE_DATA_DIR:-$PERSIST_ROOT/data}"
ENV_FILE="${VIEWTUBE_ENV_FILE:-$PERSIST_ROOT/.env.production}"
DEFAULT_CONTENT_DB_PATH="${VIEWTUBE_CONTENT_DB_PATH:-$DATA_DIR/viewtube_content.sqlite}"
DEFAULT_BEHAVIOR_DB_PATH="${VIEWTUBE_BEHAVIOR_DB_PATH:-$DATA_DIR/viewtube_behavior.sqlite}"

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
}

load_env_file "$ENV_FILE"
load_env_file "$APP_DIR/.env.production"
load_env_file "$APP_DIR/.env"

export CONTENT_DATABASE_URL="${CONTENT_DATABASE_URL:-sqlite:///$DEFAULT_CONTENT_DB_PATH}"
export BEHAVIOR_DATABASE_URL="${BEHAVIOR_DATABASE_URL:-sqlite:///$DEFAULT_BEHAVIOR_DB_PATH}"
export PYTHONPATH="$APP_DIR:$(python3 "$APP_DIR/scripts/python_deps_path.py" 2>/dev/null || printf '%s/.python_deps' "$APP_DIR")${PYTHONPATH:+:$PYTHONPATH}"

python3 "$APP_DIR/scripts/ucloud_preflight_audit.py" --strict-split --expect-persistent-root "$PERSIST_ROOT" "$@"
