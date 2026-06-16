#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import create_engine, inspect, text


CONTENT_TABLES = {"content_pools", "videos"}
BEHAVIOR_TABLES = {"users", "sessions", "impressions", "events", "search_queries"}


def sqlite_path_from_url(url: str, app_dir: Path) -> Path:
    if not url.startswith("sqlite:///"):
        raise SystemExit(f"Expected sqlite:/// URL, got: {url}")
    raw_path = url.removeprefix("sqlite:///")
    if raw_path.startswith("/"):
        return Path(unquote(raw_path))
    return app_dir / unquote(raw_path)


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:///")


def existing_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return {row[0] for row in rows}


def scalar(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> int:
    return int(connection.execute(query, params).fetchone()[0])


def write_probe(connection: sqlite3.Connection, table_name: str) -> None:
    connection.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER PRIMARY KEY, touched TEXT)')
    connection.execute(f'DELETE FROM "{table_name}"')
    connection.execute(f'INSERT INTO "{table_name}" (touched) VALUES (?)', ("ok",))
    connection.execute(f'DROP TABLE "{table_name}"')
    connection.commit()


def recent_ids(connection: sqlite3.Connection, table: str, column: str = "id", limit: int = 5) -> list[str]:
    rows = connection.execute(f"SELECT {column} FROM {table} ORDER BY ROWID DESC LIMIT {limit}").fetchall()
    return [str(row[0]) for row in rows]


def sql_tables(url: str) -> set[str]:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def sql_scalar(url: str, query: str, params: dict[str, object] | None = None) -> int:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            return int(connection.execute(text(query), params or {}).scalar() or 0)
    finally:
        engine.dispose()


def sql_recent_ids(url: str, table: str, column: str = "id", order_column: str = "id", limit: int = 5) -> list[str]:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(f'SELECT "{column}" FROM "{table}" ORDER BY "{order_column}" DESC NULLS LAST LIMIT :limit'), {"limit": limit}).fetchall()
            return [str(row[0]) for row in rows]
    finally:
        engine.dispose()


def sql_write_probe(url: str, table_name: str) -> None:
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER, touched VARCHAR)'))
            connection.execute(text(f'DELETE FROM "{table_name}"'))
            connection.execute(text(f'INSERT INTO "{table_name}" (id, touched) VALUES (1, :touched)'), {"touched": "ok"})
            connection.execute(text(f'DROP TABLE "{table_name}"'))
    finally:
        engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit UCloud SQLite setup and logging persistence.")
    parser.add_argument("--expect-persistent-root", default="/work/viewtube", help="Expected persistent root prefix.")
    parser.add_argument("--session-id", help="Optional session id to verify after a pilot run.")
    parser.add_argument("--strict-split", action="store_true", help="Fail if the DBs contain mixed content/behavior tables.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app_dir = Path(__file__).resolve().parents[1]
    content_url = os.environ.get("CONTENT_DATABASE_URL")
    behavior_url = os.environ.get("BEHAVIOR_DATABASE_URL")
    if not content_url or not behavior_url:
        raise SystemExit("CONTENT_DATABASE_URL and BEHAVIOR_DATABASE_URL must be set.")

    content_path = sqlite_path_from_url(content_url, app_dir)
    behavior_path = sqlite_path_from_url(behavior_url, app_dir) if is_sqlite_url(behavior_url) else None
    expected_root = Path(args.expect_persistent_root)

    print("=== UCloud preflight audit ===")
    print(f"CONTENT_DATABASE_URL={content_url}")
    print(f"BEHAVIOR_DATABASE_URL={behavior_url}")
    print(f"Resolved content DB: {content_path}")
    print(f"Resolved behavior DB: {behavior_path if behavior_path else 'PostgreSQL/SQL URL'}")

    if behavior_path and content_path == behavior_path:
        raise SystemExit("Content and behavior DB paths must differ.")

    for label, db_path in (("content", content_path), ("behavior", behavior_path)):
        if db_path is None:
            continue
        if not db_path.exists():
            raise SystemExit(f"{label.title()} DB does not exist: {db_path}")
        if expected_root and not str(db_path).startswith(str(expected_root)):
            raise SystemExit(f"{label.title()} DB is not under expected persistent root {expected_root}: {db_path}")

    with sqlite3.connect(content_path) as content_db:
        content_tables = existing_tables(content_db)
        if behavior_path:
            behavior_db = sqlite3.connect(behavior_path)
            behavior_tables = existing_tables(behavior_db)
        else:
            behavior_db = None
            behavior_tables = sql_tables(behavior_url)

        print(f"Content tables: {sorted(content_tables)}")
        print(f"Behavior tables: {sorted(behavior_tables)}")

        if not CONTENT_TABLES.issubset(content_tables):
            raise SystemExit(f"Content DB missing required tables: {sorted(CONTENT_TABLES - content_tables)}")
        if not BEHAVIOR_TABLES.issubset(behavior_tables):
            raise SystemExit(f"Behavior DB missing required tables: {sorted(BEHAVIOR_TABLES - behavior_tables)}")

        if args.strict_split:
            mixed_in_content = content_tables & BEHAVIOR_TABLES
            mixed_in_behavior = behavior_tables & CONTENT_TABLES
            if mixed_in_content:
                raise SystemExit(f"Content DB still contains behavior tables: {sorted(mixed_in_content)}")
            if mixed_in_behavior:
                raise SystemExit(f"Behavior DB still contains content tables: {sorted(mixed_in_behavior)}")

        write_probe(content_db, "__preflight_write_probe_content")
        if behavior_db:
            write_probe(behavior_db, "__preflight_write_probe_behavior")
        else:
            sql_write_probe(behavior_url, "__preflight_write_probe_behavior")

        videos = scalar(content_db, "SELECT COUNT(*) FROM videos")
        if behavior_db:
            sessions = scalar(behavior_db, "SELECT COUNT(*) FROM sessions")
            impressions = scalar(behavior_db, "SELECT COUNT(*) FROM impressions")
            events = scalar(behavior_db, "SELECT COUNT(*) FROM events")
            searches = scalar(behavior_db, "SELECT COUNT(*) FROM search_queries")
            recent_sessions = recent_ids(behavior_db, "sessions")
            recent_impressions = recent_ids(behavior_db, "impressions")
            recent_events = recent_ids(behavior_db, "events")
        else:
            sessions = sql_scalar(behavior_url, "SELECT COUNT(*) FROM sessions")
            impressions = sql_scalar(behavior_url, "SELECT COUNT(*) FROM impressions")
            events = sql_scalar(behavior_url, "SELECT COUNT(*) FROM events")
            searches = sql_scalar(behavior_url, "SELECT COUNT(*) FROM search_queries")
            recent_sessions = sql_recent_ids(behavior_url, "sessions", "id", "created_at")
            recent_impressions = sql_recent_ids(behavior_url, "impressions", "id", "timestamp")
            recent_events = sql_recent_ids(behavior_url, "events", "id", "timestamp")

        print(f"videos={videos}")
        print(f"sessions={sessions}")
        print(f"impressions={impressions}")
        print(f"events={events}")
        print(f"search_queries={searches}")
        print(f"Recent session IDs: {recent_sessions}")
        print(f"Recent impression IDs: {recent_impressions}")
        print(f"Recent event IDs: {recent_events}")

        if args.session_id:
            if behavior_db:
                session_count = scalar(behavior_db, "SELECT COUNT(*) FROM sessions WHERE id = ?", (args.session_id,))
                impression_count = scalar(behavior_db, "SELECT COUNT(*) FROM impressions WHERE session_id = ?", (args.session_id,))
                event_count = scalar(behavior_db, "SELECT COUNT(*) FROM events WHERE session_id = ?", (args.session_id,))
            else:
                params = {"session_id": args.session_id}
                session_count = sql_scalar(behavior_url, "SELECT COUNT(*) FROM sessions WHERE id = :session_id", params)
                impression_count = sql_scalar(behavior_url, "SELECT COUNT(*) FROM impressions WHERE session_id = :session_id", params)
                event_count = sql_scalar(behavior_url, "SELECT COUNT(*) FROM events WHERE session_id = :session_id", params)
            print(f"session_check[{args.session_id}] -> sessions={session_count}, impressions={impression_count}, events={event_count}")
            if session_count == 0:
                raise SystemExit(f"Session id not found in behavior DB: {args.session_id}")
        if behavior_db:
            behavior_db.close()

    print("Preflight audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
