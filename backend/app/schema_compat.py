from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _columns(engine: Engine, table_name: str) -> set[str]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def ensure_experimental_schema(engine: Engine) -> None:
    """Add experimental columns to existing local SQLite/Postgres dev databases.

    The project intentionally has no migration framework. This keeps the existing
    system/data intact while making older workspaces compatible with the expanded
    experimental logging contract.
    """
    is_postgres = engine.dialect.name == "postgresql"
    bool_false = "FALSE" if is_postgres else "0"
    bool_true = "TRUE" if is_postgres else "1"

    additions: dict[str, list[tuple[str, str]]] = {
        "sessions": [
            ("condition", "VARCHAR NOT NULL DEFAULT 'control_recommendation'"),
            ("survey_completed", f"BOOLEAN NOT NULL DEFAULT {bool_false}"),
            ("gender", "VARCHAR"),
            ("age", "INTEGER"),
            ("age_group", "VARCHAR"),
            ("household_living_arrangement", "VARCHAR"),
            ("education", "VARCHAR"),
            ("education_level", "VARCHAR"),
            ("region_dk", "VARCHAR"),
            ("left_right_orientation", "INTEGER"),
            ("political_orientation", "INTEGER"),
            ("video_platform_use", "VARCHAR"),
            ("typical_video_platforms", "TEXT"),
            ("cohabitation_status", "VARCHAR"),
            ("employment_status", "VARCHAR"),
            ("norstat_pid", "VARCHAR"),
            ("feminist_attitude", "INTEGER"),
            ("feminism_taken_too_far", "INTEGER"),
            ("traditional_gender_attitude", "INTEGER"),
            ("harder_to_be_a_man_today", "INTEGER"),
            ("social_division", "INTEGER"),
            ("gender_conflict_exaggeration", "INTEGER"),
            ("online_misinformation", "INTEGER"),
            ("perceived_content_type", "VARCHAR"),
            ("study_state", "VARCHAR NOT NULL DEFAULT 'entry'"),
            ("reel_duration_seconds", "INTEGER NOT NULL DEFAULT 240"),
            ("reel_started_at", "TIMESTAMP"),
            ("reel_expires_at", "TIMESTAMP"),
            ("reel_completed_at", "TIMESTAMP"),
            ("post_survey_completed_at", "TIMESTAMP"),
            ("consent_status", "VARCHAR"),
            ("consented_at", "TIMESTAMP"),
            ("screened_reason", "VARCHAR"),
            ("screened_at", "TIMESTAMP"),
            ("created_at", "TIMESTAMP"),
        ],
        "videos": [
            ("content_pool", "VARCHAR NOT NULL DEFAULT 'safe'"),
            ("youtube_id", "VARCHAR"),
            ("source", "VARCHAR DEFAULT 'youtube'"),
            ("creator_slug", "VARCHAR"),
            ("review_group", "VARCHAR"),
            ("channel_id", "VARCHAR"),
            ("ingest_source_type", "VARCHAR"),
            ("ingest_query", "VARCHAR"),
            ("short_confidence", "VARCHAR"),
            ("embeddable", f"BOOLEAN NOT NULL DEFAULT {bool_true}"),
            ("embeddable_checked_at", "TIMESTAMP"),
        ],
        "impressions": [
            ("user_id", "VARCHAR"),
            ("condition", "VARCHAR NOT NULL DEFAULT 'control_recommendation'"),
            ("content_pool", "VARCHAR NOT NULL DEFAULT 'safe'"),
            ("gender", "VARCHAR NOT NULL DEFAULT 'unspecified'"),
            ("exposure_id", "VARCHAR"),
            ("client_log_id", "VARCHAR"),
            ("client_event_at", "TIMESTAMP"),
            ("client_sequence_number", "INTEGER"),
        ],
        "events": [
            ("user_id", "VARCHAR"),
            ("condition", "VARCHAR NOT NULL DEFAULT 'control_recommendation'"),
            ("content_pool", "VARCHAR NOT NULL DEFAULT 'safe'"),
            ("gender", "VARCHAR NOT NULL DEFAULT 'unspecified'"),
            ("exposure_id", "VARCHAR"),
            ("client_log_id", "VARCHAR"),
            ("client_event_at", "TIMESTAMP"),
            ("client_sequence_number", "INTEGER"),
        ],
        "search_queries": [
            ("user_id", "VARCHAR"),
            ("condition", "VARCHAR NOT NULL DEFAULT 'control_recommendation'"),
            ("gender", "VARCHAR"),
        ],
    }

    with engine.begin() as connection:
        for table_name, table_additions in additions.items():
            existing = _columns(engine, table_name)
            if not existing:
                continue
            for column_name, ddl in table_additions:
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))

        if "impressions" in inspect(engine).get_table_names():
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_impressions_client_log_id ON impressions (client_log_id)"))
        if "events" in inspect(engine).get_table_names():
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_events_client_log_id ON events (client_log_id)"))

        if "videos" in inspect(engine).get_table_names():
            connection.execute(text("UPDATE videos SET content_pool = 'safe' WHERE content_pool IS NULL OR content_pool = ''"))
            connection.execute(text("UPDATE videos SET source = 'seed' WHERE (youtube_id IS NULL OR youtube_id = '') AND thumbnail_url LIKE 'gradient://%'"))
        if "sessions" in inspect(engine).get_table_names():
            connection.execute(text("UPDATE sessions SET condition = 'control_recommendation' WHERE condition IS NULL OR condition = ''"))
            connection.execute(text(f"UPDATE sessions SET survey_completed = {bool_false} WHERE survey_completed IS NULL"))
            connection.execute(text("UPDATE sessions SET study_state = 'entry' WHERE study_state IS NULL OR study_state = ''"))
            connection.execute(text("UPDATE sessions SET reel_duration_seconds = 240 WHERE reel_duration_seconds IS NULL OR reel_duration_seconds <= 0"))
        if "impressions" in inspect(engine).get_table_names():
            connection.execute(text("UPDATE impressions SET condition = 'control_recommendation' WHERE condition IS NULL OR condition = ''"))
            connection.execute(text("UPDATE impressions SET content_pool = 'safe' WHERE content_pool IS NULL OR content_pool = ''"))
            connection.execute(text("UPDATE impressions SET gender = 'unspecified' WHERE gender IS NULL OR gender = ''"))
        if "events" in inspect(engine).get_table_names():
            connection.execute(text("UPDATE events SET condition = 'control_recommendation' WHERE condition IS NULL OR condition = ''"))
            connection.execute(text("UPDATE events SET content_pool = 'safe' WHERE content_pool IS NULL OR content_pool = ''"))
            connection.execute(text("UPDATE events SET gender = 'unspecified' WHERE gender IS NULL OR gender = ''"))
        if "search_queries" in inspect(engine).get_table_names():
            connection.execute(text("UPDATE search_queries SET condition = 'control_recommendation' WHERE condition IS NULL OR condition = ''"))
