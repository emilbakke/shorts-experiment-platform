#!/usr/bin/env python3
"""Validate that a Norstat/study participant is linked across behavior tables."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text


def default_behavior_url() -> str:
    persist_root = Path(os.getenv("VIEWTUBE_PERSIST_ROOT", "/work/viewtube"))
    data_dir = Path(os.getenv("VIEWTUBE_DATA_DIR", str(persist_root / "data")))
    return os.getenv("BEHAVIOR_DATABASE_URL", f"sqlite:///{data_dir / 'viewtube_behavior.sqlite'}")


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rows_for_user(connection, table: str, participant_id: str) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in connection.execute(text(f'SELECT * FROM "{table}" WHERE user_id = :user_id'), {"user_id": participant_id}).fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate study behavior linkage for one participant id.")
    parser.add_argument("participant_id", help="Canonical id, e.g. norstat-TEST_EMIL2")
    parser.add_argument("--database-url", default=default_behavior_url())
    args = parser.parse_args()

    engine = create_engine(args.database_url, future=True)
    failures: list[str] = []
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            required = {"sessions", "impressions", "events", "search_queries"}
            missing = required - tables
            if missing:
                raise SystemExit(f"Missing behavior tables: {sorted(missing)}")

            sessions = rows_for_user(connection, "sessions", args.participant_id)
            impressions = rows_for_user(connection, "impressions", args.participant_id)
            events = rows_for_user(connection, "events", args.participant_id)
            searches = rows_for_user(connection, "search_queries", args.participant_id)

            study_sessions = [row for row in sessions if str(row.get("id", "")).startswith("study-")]
            if not study_sessions:
                failures.append(f"No study-* session found for user_id={args.participant_id}")
            if not impressions:
                failures.append(f"No impressions found for user_id={args.participant_id}")
            if not events:
                failures.append(f"No events found for user_id={args.participant_id}")

            session_ids = {row["id"] for row in study_sessions}
            for table_name, rows in (("impressions", impressions), ("events", events), ("search_queries", searches)):
                mismatched = sorted({row.get("session_id") for row in rows if row.get("session_id") not in session_ids})
                if mismatched:
                    failures.append(f"{table_name} contain session_id values not linked to study session(s): {mismatched}")

            windows: dict[str, tuple[datetime | None, datetime | None]] = {}
            for row in study_sessions:
                start = parse_dt(row.get("reel_started_at"))
                end = parse_dt(row.get("reel_completed_at")) or parse_dt(row.get("reel_expires_at")) or parse_dt(row.get("post_survey_completed_at"))
                windows[str(row["id"])] = (start, end)

            for table_name, rows in (("impressions", impressions), ("events", events)):
                outside = 0
                for row in rows:
                    session_id = str(row.get("session_id") or "")
                    timestamp = parse_dt(row.get("timestamp"))
                    start, end = windows.get(session_id, (None, None))
                    if timestamp and start and timestamp < start:
                        outside += 1
                    if timestamp and end and timestamp > end:
                        outside += 1
                if outside:
                    failures.append(f"{outside} {table_name} rows fall outside the stored study reel window")

            print(f"participant_id={args.participant_id}")
            print(f"sessions={len(sessions)} study_sessions={len(study_sessions)}")
            print(f"impressions={len(impressions)}")
            print(f"events={len(events)}")
            print(f"search_queries={len(searches)}")
            if failures:
                for failure in failures:
                    print(f"ERROR: {failure}")
                return 1
            print("Study behavior linkage validation passed.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
