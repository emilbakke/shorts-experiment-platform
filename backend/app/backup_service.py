from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session


CONTENT_TABLES = ["content_pools", "videos"]
BEHAVIOR_TABLES = ["users", "sessions", "impressions", "events", "search_queries"]
STATE_FILENAME = "auto-backup-state.json"


@dataclass(frozen=True)
class BackupConfig:
    content_url: str
    behavior_url: str
    backup_dir: Path
    secondary_backup_dir: Path | None
    every_n_completions: int


def _app_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def sqlite_url_to_path(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"Only sqlite:/// URLs are supported for backups, got: {url}")
    raw_path = url.removeprefix("sqlite:///")
    if raw_path.startswith("/"):
        return Path(unquote(raw_path))
    return _app_dir() / unquote(raw_path)


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:///")


def current_backup_config() -> BackupConfig:
    persist_root = Path(os.getenv("VIEWTUBE_PERSIST_ROOT", "/work/viewtube"))
    data_dir = Path(os.getenv("VIEWTUBE_DATA_DIR", str(persist_root / "data")))
    backup_dir = Path(os.getenv("VIEWTUBE_BACKUP_DIR", str(persist_root / "backups")))
    secondary_dir_raw = os.getenv("VIEWTUBE_SECONDARY_BACKUP_DIR", "").strip()
    secondary_backup_dir = Path(secondary_dir_raw) if secondary_dir_raw else None
    content_url = os.getenv("CONTENT_DATABASE_URL", f"sqlite:///{data_dir / 'viewtube_content.sqlite'}")
    behavior_url = os.getenv("BEHAVIOR_DATABASE_URL", f"sqlite:///{data_dir / 'viewtube_behavior.sqlite'}")
    every_n = int(os.getenv("VIEWTUBE_AUTO_BACKUP_EVERY_N_COMPLETIONS", "0") or "0")
    return BackupConfig(
        content_url=content_url,
        behavior_url=behavior_url,
        backup_dir=backup_dir,
        secondary_backup_dir=secondary_backup_dir,
        every_n_completions=max(0, every_n),
    )


def _state_path(backup_dir: Path) -> Path:
    return backup_dir / STATE_FILENAME


def _load_state(backup_dir: Path) -> dict[str, int]:
    path = _state_path(backup_dir)
    if not path.exists():
        return {"last_completed_count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_completed_count": 0}


def _save_state(backup_dir: Path, *, last_completed_count: int) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    _state_path(backup_dir).write_text(
        json.dumps({"last_completed_count": last_completed_count}, indent=2) + "\n",
        encoding="utf-8",
    )


def completed_session_count(db: Session) -> int:
    return int(db.execute(text("SELECT COUNT(*) FROM sessions WHERE study_state = 'complete'")).scalar() or 0)


def _backup_sqlite(db_path: Path, prefix: str, tables: list[str], backup_dir: Path, stamp: str) -> list[Path]:
    if not db_path.exists():
        raise RuntimeError(f"Database file does not exist: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    sqlite_backup = backup_dir / f"{prefix}-{stamp}.sqlite"
    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(sqlite_backup)
        try:
            source.backup(dest)
        finally:
            dest.close()
        created.append(sqlite_backup)

        existing_tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        }
        for table in tables:
            if table not in existing_tables:
                continue
            rows = source.execute(f"select * from {table}")
            csv_path = backup_dir / f"{prefix}-{table}-{stamp}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([column[0] for column in rows.description])
                writer.writerows(rows.fetchall())
            created.append(csv_path)
    finally:
        source.close()
    return created


def _backup_sqlalchemy_csv(url: str, prefix: str, tables: list[str], backup_dir: Path, stamp: str) -> list[Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            existing_tables = set(inspect(connection).get_table_names())
            for table in tables:
                if table not in existing_tables:
                    continue
                rows = connection.execute(text(f'SELECT * FROM "{table}"'))
                csv_path = backup_dir / f"{prefix}-{table}-{stamp}.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(list(rows.keys()))
                    writer.writerows(rows.fetchall())
                created.append(csv_path)
    finally:
        engine.dispose()
    return created


def _backup_database_url(url: str, prefix: str, tables: list[str], backup_dir: Path, stamp: str) -> list[Path]:
    if _is_sqlite_url(url):
        return _backup_sqlite(sqlite_url_to_path(url), prefix, tables, backup_dir, stamp)
    return _backup_sqlalchemy_csv(url, prefix, tables, backup_dir, stamp)


def _mirror_backup_files(files: list[Path], target_dir: Path) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    mirrored: list[Path] = []
    for source in files:
        destination = target_dir / source.name
        shutil.copy2(source, destination)
        mirrored.append(destination)
    return mirrored


def run_backup_now(*, reason: str) -> dict[str, object]:
    config = current_backup_config()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    created_files: list[Path] = []
    created_files.extend(_backup_database_url(config.content_url, "viewtube-content", CONTENT_TABLES, config.backup_dir, stamp))
    created_files.extend(_backup_database_url(config.behavior_url, "viewtube-behavior", BEHAVIOR_TABLES, config.backup_dir, stamp))

    mirrored_files: list[Path] = []
    if config.secondary_backup_dir:
        mirrored_files = _mirror_backup_files(created_files, config.secondary_backup_dir)

    return {
        "reason": reason,
        "backup_dir": str(config.backup_dir),
        "secondary_backup_dir": str(config.secondary_backup_dir) if config.secondary_backup_dir else None,
        "files": [str(path) for path in created_files],
        "mirrored_files": [str(path) for path in mirrored_files],
    }


def maybe_run_completion_backup(db: Session) -> dict[str, object] | None:
    config = current_backup_config()
    if config.every_n_completions <= 0:
        return None

    completed = completed_session_count(db)
    if completed <= 0 or completed % config.every_n_completions != 0:
        return None

    state = _load_state(config.backup_dir)
    if int(state.get("last_completed_count", 0)) >= completed:
        return None

    result = run_backup_now(reason=f"every_{config.every_n_completions}_completions")
    _save_state(config.backup_dir, last_completed_count=completed)
    return result


def warn_backup_failure(exc: Exception) -> None:
    print(f"WARNING: automatic backup failed: {exc}", file=sys.stderr)
