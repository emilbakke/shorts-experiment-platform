from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from scripts.migrate_behavior_sqlite_to_postgres import migrate_missing


def test_behavior_migration_copies_missing_rows_and_is_idempotent(tmp_path):
    source_engine = create_engine(f"sqlite:///{tmp_path / 'source.sqlite'}", future=True)
    target_engine = create_engine(f"sqlite:///{tmp_path / 'target.sqlite'}", future=True)
    models.Base.metadata.create_all(bind=source_engine, tables=[model.__table__ for model in models.BEHAVIOR_MODELS])
    SourceSession = sessionmaker(bind=source_engine, future=True)
    try:
        with SourceSession() as db:
            db.add(models.User(id="norstat-1003", username="norstat-1003"))
            db.add(models.Session(id="study-1003", user_id="norstat-1003", norstat_pid="1003", condition="control_recommendation", consent_status="accepted", study_state="complete"))
            db.add(models.Impression(id="impression-1003", user_id="norstat-1003", session_id="study-1003", condition="control_recommendation", video_id="video-1", video_title="Video 1", surface="shorts", click_from="shorts", content_pool="safe", gender="unspecified", rank=1, exposure_id="exposure-1", client_log_id="client-impression-1", client_sequence_number=1))
            db.add(models.Event(id="event-1003", user_id="norstat-1003", session_id="study-1003", condition="control_recommendation", video_id="video-1", video_title="Video 1", event_type="watch_start", surface="shorts", click_from="shorts", content_pool="safe", gender="unspecified", rank=1, exposure_id="exposure-1", client_log_id="client-event-1", client_sequence_number=2))
            db.commit()

        dry_total, _ = migrate_missing(source_engine, target_engine, apply=False)
        first_total, _ = migrate_missing(source_engine, target_engine, apply=True)
        second_total, _ = migrate_missing(source_engine, target_engine, apply=True)
        assert dry_total == 4
        assert first_total == 4
        assert second_total == 0

        TargetSession = sessionmaker(bind=target_engine, future=True)
        with TargetSession() as db:
            session = db.get(models.Session, "study-1003")
            assert session is not None
            assert session.norstat_pid == "1003"
            assert session.consent_status == "accepted"
            assert db.query(models.Impression).count() == 1
            assert db.query(models.Event).count() == 1
    finally:
        source_engine.dispose()
        target_engine.dispose()
