#!/usr/bin/env python3
"""Split a legacy combined ViewTube SQLite database into content + behavior DBs.

This is intended for the UCloud migration path where an existing persistent
`viewtube.sqlite` contains both videos and user-behavior logs. After the split:
- content DB keeps `content_pools` and `videos`
- behavior DB keeps `users`, `sessions`, `impressions`, `events`, `search_queries`

The link between the two databases is the stable `videos.id` value, which is
stored as `video_id` in the behavior tables.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


CONTENT_TABLES = {"content_pools", "videos"}
BEHAVIOR_TABLES = {"users", "sessions", "impressions", "events", "search_queries"}
KEEP_TABLES = CONTENT_TABLES | BEHAVIOR_TABLES


def existing_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def drop_extraneous_tables(connection: sqlite3.Connection, keep: set[str]) -> None:
    for table in existing_tables(connection):
        if table not in keep:
            connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    connection.commit()


def backup_copy(source_path: Path, target_path: Path, *, overwrite: bool) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and overwrite:
        target_path.unlink()
    elif target_path.exists():
        return
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def split_database(source_path: Path, content_path: Path, behavior_path: Path, *, force: bool) -> None:
    if not source_path.exists():
        raise SystemExit(f"Source SQLite database does not exist: {source_path}")
    if source_path.resolve() in {content_path.resolve(), behavior_path.resolve()}:
        raise SystemExit("Source and target database paths must be different")
    if not force and content_path.exists() and behavior_path.exists():
        print("Split databases already exist; nothing to do.")
        return

    content_missing = not content_path.exists()
    behavior_missing = not behavior_path.exists()

    backup_copy(source_path, content_path, overwrite=force)
    backup_copy(source_path, behavior_path, overwrite=force)

    content_db = sqlite3.connect(content_path)
    try:
        content_tables = set(existing_tables(content_db))
        if force or content_missing or content_tables & BEHAVIOR_TABLES:
            drop_extraneous_tables(content_db, CONTENT_TABLES)
            content_db.execute("VACUUM")
    finally:
        content_db.close()

    behavior_db = sqlite3.connect(behavior_path)
    try:
        behavior_tables = set(existing_tables(behavior_db))
        if force or behavior_missing or behavior_tables & CONTENT_TABLES:
            drop_extraneous_tables(behavior_db, BEHAVIOR_TABLES)
            behavior_db.execute("VACUUM")
    finally:
        behavior_db.close()

    print(f"Split {source_path} -> {content_path} + {behavior_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to legacy combined SQLite DB")
    parser.add_argument("--content-db", required=True, help="Path to output content SQLite DB")
    parser.add_argument("--behavior-db", required=True, help="Path to output behavior SQLite DB")
    parser.add_argument("--force", action="store_true", help="Overwrite existing split DB files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    split_database(
        Path(args.source).expanduser(),
        Path(args.content_db).expanduser(),
        Path(args.behavior_db).expanduser(),
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
