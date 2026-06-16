#!/usr/bin/env bash
set -euo pipefail

# Start ViewTube on UCloud. This script is designed for UCloud web-style jobs
# (including the Django app's Deployment parameter) where a public link exposes
# the configured PORT.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSIST_ROOT="${VIEWTUBE_PERSIST_ROOT:-/work/viewtube}"
DATA_DIR="${VIEWTUBE_DATA_DIR:-$PERSIST_ROOT/data}"
LOG_DIR="${VIEWTUBE_LOG_DIR:-$PERSIST_ROOT/logs}"
PID_FILE="${VIEWTUBE_PID_FILE:-$LOG_DIR/viewtube.pid}"
LEGACY_DB_PATH="${VIEWTUBE_LEGACY_DB_PATH:-$DATA_DIR/viewtube.sqlite}"
DEFAULT_CONTENT_DB_PATH="${VIEWTUBE_CONTENT_DB_PATH:-$DATA_DIR/viewtube_content.sqlite}"
DEFAULT_BEHAVIOR_DB_PATH="${VIEWTUBE_BEHAVIOR_DB_PATH:-$DATA_DIR/viewtube_behavior.sqlite}"
PORT="${PORT:-3000}"
ENV_FILE="${VIEWTUBE_ENV_FILE:-$PERSIST_ROOT/.env.production}"
VENV_DIR="${VIEWTUBE_PYTHON_VENV:-$PERSIST_ROOT/.venv}"
PY_DEPS_DIR="$(python3 "$APP_DIR/scripts/python_deps_path.py" 2>/dev/null || printf '%s/.python_deps' "$APP_DIR")"
SUPERVISE="${VIEWTUBE_SUPERVISE:-1}"
SUPERVISE_MAX_RESTARTS="${VIEWTUBE_SUPERVISE_MAX_RESTARTS:-0}"

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

load_env_file "$APP_DIR/.env.production"
load_env_file "$APP_DIR/.env"
# The persistent UCloud configuration is authoritative. Load it last so a
# repository-local development env file cannot silently override production.
load_env_file "$ENV_FILE"

mkdir -p "$DATA_DIR" "$LOG_DIR" "$PERSIST_ROOT/backups"
export CONTENT_DATABASE_URL="${CONTENT_DATABASE_URL:-sqlite:///$DEFAULT_CONTENT_DB_PATH}"
export BEHAVIOR_DATABASE_URL="${BEHAVIOR_DATABASE_URL:-sqlite:///$DEFAULT_BEHAVIOR_DB_PATH}"
export DATABASE_URL="${DATABASE_URL:-$CONTENT_DATABASE_URL}"
export VIEWTUBE_AUTO_BACKUP_EVERY_N_COMPLETIONS="${VIEWTUBE_AUTO_BACKUP_EVERY_N_COMPLETIONS:-10}"
export NEXT_TELEMETRY_DISABLED=1
export PORT

# SQLAlchemy plain postgresql:// URLs select psycopg2. UCloud installs the
# modern psycopg driver, so make that choice explicit before starting services.
if [[ "$BEHAVIOR_DATABASE_URL" == postgresql://* ]]; then
  export BEHAVIOR_DATABASE_URL="postgresql+psycopg://${BEHAVIOR_DATABASE_URL#postgresql://}"
fi

ensure_node20

cd "$APP_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "ERROR: Missing Python virtual environment at $VENV_DIR. Run scripts/ucloud_setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
PYTHON_BIN="$VENV_DIR/bin/python"
export PATH="$VENV_DIR/bin:$PATH"
export PYTHON_BIN
export PYTHONPATH="$PY_DEPS_DIR:$APP_DIR/.python_deps:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
echo "Using Python virtual environment: $VENV_DIR"

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
  fi
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, sqlalchemy, psycopg" >/dev/null 2>&1; then
  echo "ERROR: Missing Python backend dependencies in $VENV_DIR. Run scripts/ucloud_setup.sh first." >&2
  exit 1
fi

ensure_frontend_build_current

BACKEND_HOST="${VIEWTUBE_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${VIEWTUBE_BACKEND_PORT:-8000}"
BACKEND_LOG_LEVEL="${VIEWTUBE_BACKEND_LOG_LEVEL:-warning}"
BACKEND_ACCESS_LOG="${VIEWTUBE_BACKEND_ACCESS_LOG:-0}"
export BACKEND_URL="${BACKEND_URL:-http://$BACKEND_HOST:$BACKEND_PORT}"
export VIEWTUBE_BACKEND_MODE="${VIEWTUBE_BACKEND_MODE:-http}"

if [[ "$VIEWTUBE_BACKEND_MODE" != "http" ]]; then
  echo "ERROR: UCloud production must use VIEWTUBE_BACKEND_MODE=http; refusing SQLite subprocess fallback." >&2
  exit 1
fi
if [[ "${VIEWTUBE_REQUIRE_POSTGRES_BEHAVIOR:-1}" == "1" && "$BEHAVIOR_DATABASE_URL" != postgresql* ]]; then
  echo "ERROR: UCloud production requires PostgreSQL BEHAVIOR_DATABASE_URL; got $BEHAVIOR_DATABASE_URL" >&2
  exit 1
fi

list_listener_pids_for_ports() {
  "$PYTHON_BIN" - "$@" <<'PY'
import os
import socket
import sys

ports = {int(port) for port in sys.argv[1:]}
inodes: set[str] = set()

def collect(path: str) -> None:
    try:
        rows = open(path, encoding="utf-8").read().splitlines()[1:]
    except FileNotFoundError:
        return
    for row in rows:
        parts = row.split()
        if len(parts) < 10 or parts[3] != "0A":
            continue
        local_address = parts[1]
        try:
            port = int(local_address.rsplit(":", 1)[1], 16)
        except ValueError:
            continue
        if port in ports:
            inodes.add(parts[9])

collect("/proc/net/tcp")
collect("/proc/net/tcp6")

pids: set[int] = set()
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except (FileNotFoundError, PermissionError):
        continue
    for fd in fds:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            pids.add(int(pid))
            break

for pid in sorted(pids):
    print(pid)
PY
}

kill_stale_viewtube_processes() {
  if [[ "${VIEWTUBE_KILL_STALE_ON_START:-1}" != "1" ]]; then
    return 0
  fi

  echo "Checking for stale ViewTube processes before start."
  local current_pid="$$"
  local stale_pids=()
  local pid args

  while read -r pid args; do
    [[ -z "${pid:-}" ]] && continue
    [[ "$pid" == "$current_pid" ]] && continue
    if [[ "$args" == *"$APP_DIR/scripts/ucloud_start.sh"* ]] ||
       [[ "$args" == *"scripts/ucloud_start.sh"* ]] ||
       [[ "$args" == *"next start"*"--port $PORT"* ]] ||
       [[ "$args" == *"next-server"* ]] ||
       [[ "$args" == *"uvicorn"*"backend.app.main:app"*"--port $BACKEND_PORT"* ]]; then
      stale_pids+=("$pid")
    fi
  done < <(ps -eo pid=,args=)

  while read -r pid; do
    [[ -z "${pid:-}" ]] && continue
    [[ "$pid" == "$current_pid" ]] && continue
    stale_pids+=("$pid")
  done < <(list_listener_pids_for_ports "$PORT" "$BACKEND_PORT")

  if [[ "${#stale_pids[@]}" -eq 0 ]]; then
    return 0
  fi

  mapfile -t stale_pids < <(printf "%s\n" "${stale_pids[@]}" | sort -n -u)
  echo "Stopping stale ViewTube process(es): ${stale_pids[*]}"
  kill "${stale_pids[@]}" >/dev/null 2>&1 || true
  sleep 2

  local still_running=()
  for pid in "${stale_pids[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      still_running+=("$pid")
    fi
  done

  if [[ "${#still_running[@]}" -gt 0 ]]; then
    echo "Force-stopping stale ViewTube process(es): ${still_running[*]}"
    kill -9 "${still_running[@]}" >/dev/null 2>&1 || true
  fi

  rm -f "$PID_FILE"
}

kill_stale_viewtube_processes

backend_pid=""
frontend_pid=""

stop_processes() {
  local reason="${1:-shutdown}"
  if [[ -n "${frontend_pid:-}" ]] && kill -0 "$frontend_pid" >/dev/null 2>&1; then
    echo "Stopping Next.js frontend PID $frontend_pid ($reason)."
    kill "$frontend_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "${backend_pid:-}" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
    echo "Stopping FastAPI backend PID $backend_pid ($reason)."
    kill "$backend_pid" >/dev/null 2>&1 || true
  fi
  [[ -n "${frontend_pid:-}" ]] && wait "$frontend_pid" >/dev/null 2>&1 || true
  [[ -n "${backend_pid:-}" ]] && wait "$backend_pid" >/dev/null 2>&1 || true
  frontend_pid=""
  backend_pid=""
}

terminate_children() {
  echo "Received shutdown signal."
  stop_processes "signal"
  exit 0
}

trap terminate_children INT TERM

wait_for_backend() {
  local attempts="${VIEWTUBE_BACKEND_HEALTH_ATTEMPTS:-60}"
  local delay="${VIEWTUBE_BACKEND_HEALTH_DELAY:-1}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if "$PYTHON_BIN" - "$BACKEND_URL/health" <<'PY' >/dev/null 2>&1
import json
import sys
from urllib.request import urlopen
with urlopen(sys.argv[1], timeout=2) as response:
    data = json.loads(response.read().decode("utf-8"))
if data.get("ok") is not True:
    raise SystemExit(1)
if data.get("behavior_database") != "postgresql":
    raise SystemExit(1)
PY
    then
      return 0
    fi
    if [[ -n "${backend_pid:-}" ]] && ! kill -0 "$backend_pid" >/dev/null 2>&1; then
      return 1
    fi
    sleep "$delay"
  done
  return 1
}

start_backend() {
  echo "Starting FastAPI backend on $BACKEND_URL"
  uvicorn_args=(backend.app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --log-level "$BACKEND_LOG_LEVEL")
  if [[ "$BACKEND_ACCESS_LOG" != "1" ]]; then
    uvicorn_args+=(--no-access-log)
  fi
  "$PYTHON_BIN" -m uvicorn "${uvicorn_args[@]}" &
  backend_pid="$!"
  if ! wait_for_backend; then
    echo "ERROR: FastAPI backend did not become healthy at $BACKEND_URL/health." >&2
    stop_processes "backend health check failed"
    return 1
  fi
  echo "FastAPI backend healthy (PID $backend_pid)."
}

start_frontend() {
  echo "Starting Next.js frontend on 0.0.0.0:$PORT"
  npm --prefix frontend run start -- --hostname 0.0.0.0 --port "$PORT" &
  frontend_pid="$!"
  echo "Next.js frontend started (PID $frontend_pid)."
}

wait_for_pair_exit() {
  local backend_status=0
  local frontend_status=0
  while true; do
    if [[ -n "${backend_pid:-}" ]] && ! kill -0 "$backend_pid" >/dev/null 2>&1; then
      wait "$backend_pid" || backend_status="$?"
      echo "FastAPI backend PID $backend_pid exited with code $backend_status."
      stop_processes "backend exited"
      return "$backend_status"
    fi
    if [[ -n "${frontend_pid:-}" ]] && ! kill -0 "$frontend_pid" >/dev/null 2>&1; then
      wait "$frontend_pid" || frontend_status="$?"
      echo "Next.js frontend PID $frontend_pid exited with code $frontend_status."
      stop_processes "frontend exited"
      return "$frontend_status"
    fi
    sleep 2
  done
}

run_once() {
  echo "Frontend port: $PORT"
  echo "Backend URL: $BACKEND_URL"
  echo "Content DB: $CONTENT_DATABASE_URL"
  echo "Behavior DB: $BEHAVIOR_DATABASE_URL"
  echo "Backend mode: $VIEWTUBE_BACKEND_MODE"

  if [[ "$VIEWTUBE_BACKEND_MODE" == "http" ]]; then
    start_backend || return $?
    echo "Backend PID: $backend_pid"
  else
    echo "Backend PID: subprocess fallback mode (no persistent backend)."
  fi

  start_frontend
  echo "Frontend PID: $frontend_pid"
  wait_for_pair_exit
}

if [[ "$SUPERVISE" != "1" ]]; then
  run_once
  exit "$?"
fi

restart_count=0
while true; do
  start_ts="$(date -Is)"
  echo "[$start_ts] Launching ViewTube services (restart_count=$restart_count)."
  set +e
  run_once
  exit_code="$?"
  set -e
  stop_ts="$(date -Is)"
  echo "[$stop_ts] ViewTube services exited with code $exit_code."

  if [[ "$exit_code" -eq 0 ]]; then
    echo "ViewTube services exited cleanly; not restarting."
    exit 0
  fi

  restart_count=$((restart_count + 1))
  if [[ "$SUPERVISE_MAX_RESTARTS" != "0" && "$restart_count" -gt "$SUPERVISE_MAX_RESTARTS" ]]; then
    echo "ViewTube services exceeded VIEWTUBE_SUPERVISE_MAX_RESTARTS=$SUPERVISE_MAX_RESTARTS; exiting." >&2
    exit "$exit_code"
  fi

  if [[ "$restart_count" -lt 3 ]]; then
    sleep_seconds=5
  elif [[ "$restart_count" -lt 6 ]]; then
    sleep_seconds=15
  else
    sleep_seconds=30
  fi
  echo "Restarting ViewTube services in ${sleep_seconds}s. If this repeats, inspect UCloud logs for the first crash above."
  sleep "$sleep_seconds"
done
