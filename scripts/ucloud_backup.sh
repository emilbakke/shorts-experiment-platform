#!/usr/bin/env bash
set -euo pipefail

# Export timestamped SQLite backups and CSV extracts from the persistent
# ViewTube databases on UCloud.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERSIST_ROOT="${VIEWTUBE_PERSIST_ROOT:-/work/viewtube}"
DATA_DIR="${VIEWTUBE_DATA_DIR:-$PERSIST_ROOT/data}"
BACKUP_DIR="${VIEWTUBE_BACKUP_DIR:-$PERSIST_ROOT/backups}"
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
mkdir -p "$BACKUP_DIR"

python3 - "$APP_DIR" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

app_dir = Path(sys.argv[1])
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from backend.app.backup_service import run_backup_now  # noqa: E402

result = run_backup_now(reason="manual_script")
print(f"Wrote backup files to {result['backup_dir']}")
for path in result["files"]:
    print(path)
if result.get("mirrored_files"):
    print(f"Mirrored backup files to {result['secondary_backup_dir']}")
    for path in result["mirrored_files"]:
        print(path)
PY
