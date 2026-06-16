#!/usr/bin/env python3
"""Copy missing behavior records from SQLite into PostgreSQL, preserving IDs.

The operation is idempotent: existing primary-key IDs in PostgreSQL are skipped.
Use --apply to perform writes; without it the script only reports a plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.schema_compat import ensure_experimental_schema

ORDERED_MODELS = (models.User, models.Session, models.Impression, models.Event, models.SearchQuery)


def migrate_missing(source_engine, target_engine, *, apply: bool) -> tuple[int, dict[str, int]]:
    models.Base.metadata.create_all(bind=target_engine, tables=[model.__table__ for model in models.BEHAVIOR_MODELS])
    ensure_experimental_schema(target_engine)
    SourceSession = sessionmaker(bind=source_engine, future=True)
    TargetSession = sessionmaker(bind=target_engine, future=True)
    total_missing = 0
    missing_by_table: dict[str, int] = {}
    with SourceSession() as source_db, TargetSession() as target_db:
        for model in ORDERED_MODELS:
            source_rows = source_db.query(model).all()
            existing_ids = {row[0] for row in target_db.query(model.id).all()}
            missing_rows = [row for row in source_rows if row.id not in existing_ids]
            missing_by_table[model.__tablename__] = len(missing_rows)
            total_missing += len(missing_rows)
            print(f"{model.__tablename__}: source={len(source_rows)} target_existing={len(existing_ids)} missing={len(missing_rows)}")
            if not apply:
                continue
            columns = [column.key for column in model.__table__.columns]
            for row in missing_rows:
                target_db.add(model(**{column: getattr(row, column) for column in columns}))
            target_db.commit()
    return total_missing, missing_by_table


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy missing ViewTube behavior rows from SQLite to PostgreSQL.")
    parser.add_argument("--source", default="sqlite:////work/viewtube/data/viewtube_behavior.sqlite")
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true", help="Write missing rows. Default is dry-run.")
    args = parser.parse_args()

    if not args.source.startswith("sqlite:"):
        raise SystemExit("Source must be SQLite.")
    if not args.target.startswith("postgresql"):
        raise SystemExit("Target must be PostgreSQL.")
    source_path = Path(args.source.removeprefix("sqlite:///"))
    if not source_path.exists():
        raise SystemExit(f"Source SQLite database does not exist: {source_path}")

    source_engine = create_engine(args.source, future=True)
    target_engine = create_engine(args.target, future=True, pool_pre_ping=True)
    try:
        total_missing, _ = migrate_missing(source_engine, target_engine, apply=args.apply)
        print(f"Total missing rows: {total_missing}")
        print("Migration applied." if args.apply else "Dry run only; rerun with --apply to copy rows.")
        return 0
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
