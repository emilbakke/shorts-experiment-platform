from __future__ import annotations

import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_UCLOUD_ROOT = REPO_ROOT / ".local-ucloud"
LOCAL_DATA_DIR = LOCAL_UCLOUD_ROOT / "data"
LEGACY_DB_PATH = REPO_ROOT / "backend" / "app.db"
DEFAULT_CONTENT_DB_PATH = LOCAL_DATA_DIR / "viewtube_content.sqlite"
DEFAULT_BEHAVIOR_DB_PATH = LOCAL_DATA_DIR / "viewtube_behavior.sqlite"

CONTENT_TABLES = {"content_pools", "videos"}
BEHAVIOR_TABLES = {"users", "sessions", "impressions", "events", "search_queries"}


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _existing_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _drop_extraneous_tables(connection: sqlite3.Connection, keep: set[str]) -> None:
    for table in _existing_tables(connection):
        if table not in keep:
            connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.commit()


def _backup_copy(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def ensure_local_split_databases() -> tuple[Path, Path]:
    """Mirror the UCloud split SQLite layout for default local development.

    If explicit database URLs are supplied, the caller should bypass this helper.
    Otherwise we create `.local-ucloud/data/viewtube_content.sqlite` and
    `.local-ucloud/data/viewtube_behavior.sqlite` on first use by splitting the
    legacy combined `backend/app.db` database.
    """

    if not LEGACY_DB_PATH.exists():
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_CONTENT_DB_PATH, DEFAULT_BEHAVIOR_DB_PATH

    if not DEFAULT_CONTENT_DB_PATH.exists():
        _backup_copy(LEGACY_DB_PATH, DEFAULT_CONTENT_DB_PATH)
        content_db = sqlite3.connect(DEFAULT_CONTENT_DB_PATH)
        try:
            _drop_extraneous_tables(content_db, CONTENT_TABLES)
            content_db.execute("VACUUM")
        finally:
            content_db.close()

    if not DEFAULT_BEHAVIOR_DB_PATH.exists():
        _backup_copy(LEGACY_DB_PATH, DEFAULT_BEHAVIOR_DB_PATH)
        behavior_db = sqlite3.connect(DEFAULT_BEHAVIOR_DB_PATH)
        try:
            _drop_extraneous_tables(behavior_db, BEHAVIOR_TABLES)
            behavior_db.execute("VACUUM")
        finally:
            behavior_db.close()

    return DEFAULT_CONTENT_DB_PATH, DEFAULT_BEHAVIOR_DB_PATH


def default_database_urls() -> tuple[str, str, str]:
    content_path, behavior_path = ensure_local_split_databases()
    content_url = _sqlite_url(content_path)
    behavior_url = _sqlite_url(behavior_path)
    return content_url, behavior_url, content_url
