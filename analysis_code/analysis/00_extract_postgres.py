#!/usr/bin/env python3
"""Extract raw behavior PostgreSQL tables and optional content metadata.

Usage:
  VIEWTUBE_BEHAVIOR_DATABASE_URL='postgresql+psycopg://...' python analysis/00_extract_postgres.py

Optional:
  VIEWTUBE_CONTENT_DATABASE_URL='sqlite:///data/viewtube_content.sqlite'
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from common import BEHAVIOR_TABLES, CONTENT_TABLES, LOG_DIR, RAW_DIR, ensure_output_dirs, write_text


def export_tables(database_url: str, table_names: list[str], label: str) -> list[str]:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    available = set(inspector.get_table_names())
    lines: list[str] = [f"[{label}] database_url_scheme={database_url.split(':', 1)[0]}"]
    with engine.connect() as conn:
        for table in table_names:
            if table not in available:
                lines.append(f"{table}: MISSING")
                continue
            df = pd.read_sql_query(text(f'SELECT * FROM "{table}"'), conn)
            out = RAW_DIR / f"{table}.csv"
            df.to_csv(out, index=False)
            min_ts = max_ts = ""
            for ts_col in ["timestamp", "created_at", "started_at"]:
                if ts_col in df.columns and not df.empty:
                    parsed = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
                    min_ts = str(parsed.min())
                    max_ts = str(parsed.max())
                    break
            lines.append(f"{table}: rows={len(df)} cols={len(df.columns)} min_ts={min_ts} max_ts={max_ts} -> {out}")
    return lines


def main() -> None:
    ensure_output_dirs()
    behavior_url = os.environ.get("VIEWTUBE_BEHAVIOR_DATABASE_URL") or os.environ.get("BEHAVIOR_DATABASE_URL")
    if not behavior_url:
        raise SystemExit("Set VIEWTUBE_BEHAVIOR_DATABASE_URL before extracting data.")

    lines = [f"Extraction timestamp: {datetime.now(timezone.utc).isoformat()}"]
    lines += export_tables(behavior_url, BEHAVIOR_TABLES, "behavior")

    content_url = os.environ.get("VIEWTUBE_CONTENT_DATABASE_URL") or os.environ.get("CONTENT_DATABASE_URL")
    if content_url:
        lines += export_tables(content_url, CONTENT_TABLES, "content")
    else:
        lines.append("[content] skipped: set VIEWTUBE_CONTENT_DATABASE_URL to export videos/content_pools.")

    write_text(LOG_DIR / "extraction_summary.txt", "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
