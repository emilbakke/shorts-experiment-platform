#!/usr/bin/env bash
set -euo pipefail

# Start ViewTube as a background process on UCloud and persist stdout/stderr to
# a log file. This is for manual debugging from an interactive terminal that may
# disconnect. For live participant access, prefer putting scripts/ucloud_start.sh
# in the UCloud app Deployment field.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSIST_ROOT="${VIEWTUBE_PERSIST_ROOT:-/work/viewtube}"
LOG_DIR="${VIEWTUBE_LOG_DIR:-$PERSIST_ROOT/logs}"
PID_FILE="${VIEWTUBE_PID_FILE:-$LOG_DIR/viewtube.pid}"
LOG_FILE="${VIEWTUBE_SERVER_LOG:-$LOG_DIR/server.log}"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    echo "ViewTube already appears to be running as PID $old_pid."
    echo "Log: $LOG_FILE"
    exit 0
  fi
fi

cd "$APP_DIR"
nohup scripts/ucloud_start.sh >> "$LOG_FILE" 2>&1 &
pid="$!"
printf "%s\n" "$pid" > "$PID_FILE"

echo "Started ViewTube as PID $pid"
echo "Log: $LOG_FILE"
echo "Follow logs with: tail -n 200 -f $LOG_FILE"
