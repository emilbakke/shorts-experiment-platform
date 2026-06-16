#!/usr/bin/env bash
set -euo pipefail

# Prepare ViewTube for a UCloud web job. Run from inside the repository after
# the repo has been cloned/mounted in the UCloud project folder.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSIST_ROOT="${VIEWTUBE_PERSIST_ROOT:-/work/viewtube}"
DATA_DIR="${VIEWTUBE_DATA_DIR:-$PERSIST_ROOT/data}"
LOG_DIR="${VIEWTUBE_LOG_DIR:-$PERSIST_ROOT/logs}"
LEGACY_DB_PATH="${VIEWTUBE_LEGACY_DB_PATH:-$DATA_DIR/viewtube.sqlite}"
DEFAULT_CONTENT_DB_PATH="${VIEWTUBE_CONTENT_DB_PATH:-$DATA_DIR/viewtube_content.sqlite}"
DEFAULT_BEHAVIOR_DB_PATH="${VIEWTUBE_BEHAVIOR_DB_PATH:-$DATA_DIR/viewtube_behavior.sqlite}"
PORT="${PORT:-3000}"
ENV_FILE="${VIEWTUBE_ENV_FILE:-$PERSIST_ROOT/.env.production}"
VENV_DIR="${VIEWTUBE_PYTHON_VENV:-$PERSIST_ROOT/.venv}"
PY_DEPS_DIR="$(python3 "$APP_DIR/scripts/python_deps_path.py" 2>/dev/null || printf '%s/.python_deps' "$APP_DIR")"

# shellcheck source=scripts/ucloud_node20.sh
source "$APP_DIR/scripts/ucloud_node20.sh"
# shellcheck source=scripts/ucloud_frontend_build.sh
source "$APP_DIR/scripts/ucloud_frontend_build.sh"

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

mkdir -p "$DATA_DIR" "$LOG_DIR" "$PERSIST_ROOT/backups"
export CONTENT_DATABASE_URL="${CONTENT_DATABASE_URL:-sqlite:///$DEFAULT_CONTENT_DB_PATH}"
export BEHAVIOR_DATABASE_URL="${BEHAVIOR_DATABASE_URL:-sqlite:///$DEFAULT_BEHAVIOR_DB_PATH}"
export DATABASE_URL="${DATABASE_URL:-$CONTENT_DATABASE_URL}"
export NEXT_TELEMETRY_DISABLED=1
export PORT

ensure_node20

cd "$APP_DIR"

ensure_python_venv() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Creating Python virtual environment at $VENV_DIR"
    if ! python3 -m venv "$VENV_DIR"; then
      echo "ERROR: Could not create Python virtual environment with python3 -m venv." >&2
      echo "On Ubuntu VMs this requires the python3-venv/ensurepip components in the image." >&2
      echo "Pick a Python-enabled VM image or ask UCloud/SDU IT for python3-venv support; no sudo install is attempted by this script." >&2
      exit 1
    fi
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  PYTHON_BIN="$VENV_DIR/bin/python"
  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo "ERROR: Virtual environment was created, but pip is unavailable inside it." >&2
    exit 1
  fi
  export PATH="$VENV_DIR/bin:$PATH"
  export PYTHON_BIN
  export PYTHONPATH="$PY_DEPS_DIR:$APP_DIR/.python_deps:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
  echo "Using Python virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m pip install --upgrade pip
}

ensure_python_venv

if [[ "${VIEWTUBE_AUTO_SPLIT_DBS:-1}" == "1" && -f "$LEGACY_DB_PATH" ]]; then
  if [[ "$CONTENT_DATABASE_URL" == sqlite:///* && "$BEHAVIOR_DATABASE_URL" == sqlite:///* ]]; then
    content_path="${CONTENT_DATABASE_URL#sqlite:///}"
    behavior_path="${BEHAVIOR_DATABASE_URL#sqlite:///}"
    if [[ ! -f "$content_path" || ! -f "$behavior_path" ]]; then
      echo "Splitting legacy combined SQLite into content + behavior databases."
      "$PYTHON_BIN" scripts/split_sqlite_databases.py \
        --source "$LEGACY_DB_PATH" \
        --content-db "$content_path" \
        --behavior-db "$behavior_path"
    fi
  else
    echo "Skipping automatic legacy SQLite split because at least one configured DB URL is not SQLite."
    echo "If needed, create the content SQLite snapshot separately and let the app create PostgreSQL behavior tables on startup."
  fi
fi

echo "Installing Python backend dependencies into $VENV_DIR"
"$PYTHON_BIN" -m pip install --upgrade --force-reinstall -r "$APP_DIR/backend/requirements-test.txt"

echo "Installing Node dependencies"
npm ci
npm --prefix frontend ci

if [[ "${RUN_YOUTUBE_INGEST:-0}" == "1" ]]; then
  if [[ -z "${API_KEY_YOUTUBE:-}" ]]; then
    echo "RUN_YOUTUBE_INGEST=1 but API_KEY_YOUTUBE is missing; skipping ingestion." >&2
  else
    echo "Running Danish YouTube ingestion into persistent database."
    ingest_args=(
      --max-pages "${YOUTUBE_INGEST_MAX_PAGES:-10}"
      --max-total-candidates "${YOUTUBE_INGEST_MAX_TOTAL_CANDIDATES:-4000}"
      --max-duration "${YOUTUBE_INGEST_MAX_DURATION:-7200}"
    )
    if [[ "${YOUTUBE_INGEST_REQUIRE_DANISH_SIGNAL:-1}" == "1" ]]; then
      ingest_args+=(--require-danish-signal)
    fi
    "$PYTHON_BIN" scripts/ingest_youtube.py "${ingest_args[@]}"
  fi
fi

build_frontend

echo "UCloud setup complete. Start with: scripts/ucloud_start.sh"
