from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models
from backend.app.backup_service import maybe_run_completion_backup


def create_sqlite_db(path: Path, *, behavior: bool) -> None:
    engine = create_engine(f"sqlite:///{path}", future=True)
    try:
        table_models = models.BEHAVIOR_MODELS if behavior else models.CONTENT_MODELS
        models.Base.metadata.create_all(bind=engine, tables=[model.__table__ for model in table_models])
        db = sessionmaker(bind=engine, future=True)()
        try:
            if behavior:
                db.add(models.Session(id="seed-01", condition="control_recommendation", study_state="entry"))
            else:
                db.add(models.ContentPool(id="pool-1", name="safe", description="safe"))
                db.add(
                    models.Video(
                        id="video-1",
                        content_pool="safe",
                        title="Video 1",
                        channel="Channel 1",
                        topic="topic",
                        thumbnail_url="https://example.com/thumb.jpg",
                        video_url="https://example.com/video",
                        duration_seconds=10,
                        views=1,
                        popularity_score=0.1,
                        freshness_score=0.1,
                        is_short=True,
                    )
                )
            db.commit()
        finally:
            db.close()
    finally:
        engine.dispose()


def count_files(path: Path, glob_pattern: str) -> int:
    return len(list(path.glob(glob_pattern)))


def test_auto_backup_runs_on_tenth_completed_session_and_mirrors(monkeypatch, tmp_path):
    content_db_path = tmp_path / "content.sqlite"
    behavior_db_path = tmp_path / "behavior.sqlite"
    backup_dir = tmp_path / "backups"
    mirror_dir = tmp_path / "mirror"
    create_sqlite_db(content_db_path, behavior=False)
    create_sqlite_db(behavior_db_path, behavior=True)

    engine = create_engine(f"sqlite:///{behavior_db_path}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        for index in range(10):
            db.add(
                models.Session(
                    id=f"complete-{index}",
                    condition="control_recommendation",
                    study_state="complete",
                )
            )
        db.commit()

        monkeypatch.setenv("CONTENT_DATABASE_URL", f"sqlite:///{content_db_path}")
        monkeypatch.setenv("BEHAVIOR_DATABASE_URL", f"sqlite:///{behavior_db_path}")
        monkeypatch.setenv("VIEWTUBE_BACKUP_DIR", str(backup_dir))
        monkeypatch.setenv("VIEWTUBE_SECONDARY_BACKUP_DIR", str(mirror_dir))
        monkeypatch.setenv("VIEWTUBE_AUTO_BACKUP_EVERY_N_COMPLETIONS", "10")

        result = maybe_run_completion_backup(db)
        assert result is not None
        assert result["secondary_backup_dir"] == str(mirror_dir)
        assert count_files(backup_dir, "viewtube-*.sqlite") == 2
        assert count_files(mirror_dir, "viewtube-*.sqlite") == 2

        state = json.loads((backup_dir / "auto-backup-state.json").read_text(encoding="utf-8"))
        assert state["last_completed_count"] == 10

        second = maybe_run_completion_backup(db)
        assert second is None
    finally:
        db.close()
        engine.dispose()


def test_auto_backup_skips_non_threshold_counts(monkeypatch, tmp_path):
    content_db_path = tmp_path / "content.sqlite"
    behavior_db_path = tmp_path / "behavior.sqlite"
    backup_dir = tmp_path / "backups"
    create_sqlite_db(content_db_path, behavior=False)
    create_sqlite_db(behavior_db_path, behavior=True)

    engine = create_engine(f"sqlite:///{behavior_db_path}", future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        for index in range(9):
            db.add(
                models.Session(
                    id=f"complete-{index}",
                    condition="control_recommendation",
                    study_state="complete",
                )
            )
        db.commit()

        monkeypatch.setenv("CONTENT_DATABASE_URL", f"sqlite:///{content_db_path}")
        monkeypatch.setenv("BEHAVIOR_DATABASE_URL", f"sqlite:///{behavior_db_path}")
        monkeypatch.setenv("VIEWTUBE_BACKUP_DIR", str(backup_dir))
        monkeypatch.setenv("VIEWTUBE_AUTO_BACKUP_EVERY_N_COMPLETIONS", "10")

        assert maybe_run_completion_backup(db) is None
        assert not backup_dir.exists()
    finally:
        db.close()
        engine.dispose()
