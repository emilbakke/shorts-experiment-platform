#!/usr/bin/env python3
"""Fail-fast prelaunch audit for the Shorts/manosphere UCloud study DB.

Run after completing a fresh test participant in the deployed app, e.g.:

  python3 scripts/prelaunch_study_audit.py --participant-id norstat-DBFIX3 \
    --database-url 'postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE'

The script intentionally exits non-zero on any launch-blocking problem.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from typing import Any

from sqlalchemy import create_engine, inspect, text

REQUIRED_SESSION_COLUMNS = {
    "id",
    "user_id",
    "condition",
    "gender",
    "study_state",
    "survey_completed",
    "reel_started_at",
    "reel_completed_at",
    "post_survey_completed_at",
    "age_group",
    "education_level",
    "political_orientation",
    "video_platform_use",
    "typical_video_platforms",
    "cohabitation_status",
    "employment_status",
    "norstat_pid",
    "consent_status",
    "consented_at",
    "screened_reason",
    "screened_at",
    "feminist_attitude",
    "feminism_taken_too_far",
    "traditional_gender_attitude",
    "harder_to_be_a_man_today",
    "social_division",
    "gender_conflict_exaggeration",
    "online_misinformation",
    "perceived_content_type",
}

PRE_SURVEY_COLUMNS = [
    "gender",
    "age_group",
    "education_level",
    "political_orientation",
    "video_platform_use",
    "cohabitation_status",
    "employment_status",
]

POST_SURVEY_COLUMNS = [
    "feminist_attitude",
    "feminism_taken_too_far",
    "traditional_gender_attitude",
    "harder_to_be_a_man_today",
    "social_division",
    "gender_conflict_exaggeration",
    "online_misinformation",
    "perceived_content_type",
]

REQUIRED_BEHAVIOR_TABLES = {"users", "sessions", "impressions", "events", "search_queries"}


def default_database_url() -> str:
    return (
        os.getenv("VIEWTUBE_BEHAVIOR_DATABASE_URL")
        or os.getenv("BEHAVIOR_DATABASE_URL")
        or "postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE"
    )


def canonical_participant_id(raw: str) -> str:
    return raw if raw.startswith("norstat-") else f"norstat-{raw}"


def scalar(connection, sql: str, params: dict[str, Any] | None = None) -> int:
    return int(connection.execute(text(sql), params or {}).scalar() or 0)


def rows(connection, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in connection.execute(text(sql), params or {}).fetchall()]


def missing_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one completed test participant before Norstat launch.")
    parser.add_argument("--participant-id", required=True, help="Norstat pid or canonical norstat-* user_id, e.g. DBFIX3 or norstat-DBFIX3")
    parser.add_argument("--database-url", default=default_database_url())
    parser.add_argument("--min-impressions", type=int, default=20)
    parser.add_argument("--require-clicks", action="store_true", help="Also require at least one click/swipe event.")
    args = parser.parse_args()

    participant_id = canonical_participant_id(args.participant_id)
    engine = create_engine(args.database_url, future=True)
    failures: list[str] = []

    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            missing_tables = REQUIRED_BEHAVIOR_TABLES - tables
            if missing_tables:
                failures.append(f"Missing behavior tables: {sorted(missing_tables)}")

            session_columns = {column["name"] for column in inspector.get_columns("sessions")} if "sessions" in tables else set()
            missing_columns = REQUIRED_SESSION_COLUMNS - session_columns
            if missing_columns:
                failures.append(f"sessions table missing required survey columns: {sorted(missing_columns)}")

            print("=== ViewTube prelaunch study audit ===")
            print(f"participant_id={participant_id}")
            print(f"database_url_scheme={args.database_url.split(':', 1)[0]}")
            print(f"behavior_tables_present={sorted(tables & REQUIRED_BEHAVIOR_TABLES)}")
            print(f"required_session_columns_present={len(REQUIRED_SESSION_COLUMNS - missing_columns)}/{len(REQUIRED_SESSION_COLUMNS)}")

            if missing_tables or missing_columns:
                for failure in failures:
                    print(f"ERROR: {failure}")
                return 1

            sessions = rows(
                connection,
                """
                SELECT *
                FROM sessions
                WHERE user_id = :participant_id
                ORDER BY created_at DESC NULLS LAST
                """,
                {"participant_id": participant_id},
            )
            print(f"sessions_for_participant={len(sessions)}")
            if not sessions:
                failures.append("No session found for this participant. Did you use the same pid?")
                for failure in failures:
                    print(f"ERROR: {failure}")
                return 1

            session = sessions[0]
            session_id = str(session["id"])
            print(f"latest_session_id={session_id}")
            print(f"condition={session.get('condition')}")
            print(f"study_state={session.get('study_state')}")
            print(f"post_survey_completed_at={session.get('post_survey_completed_at')}")

            if not session_id.startswith("study-"):
                failures.append(f"Latest participant session is not a study-* session: {session_id}")
            if session.get("study_state") != "complete":
                failures.append(f"Latest study session is not complete: {session.get('study_state')}")
            if missing_value(session.get("post_survey_completed_at")):
                failures.append("post_survey_completed_at is missing on completed session")
            if session.get("consent_status") != "accepted":
                failures.append(f"Completed session does not record accepted consent: {session.get('consent_status')}")
            if missing_value(session.get("consented_at")):
                failures.append("consented_at is missing on completed session")

            missing_pre = [col for col in PRE_SURVEY_COLUMNS if missing_value(session.get(col))]
            missing_post = [col for col in POST_SURVEY_COLUMNS if missing_value(session.get(col))]
            print(f"pre_survey_fields_present={len(PRE_SURVEY_COLUMNS) - len(missing_pre)}/{len(PRE_SURVEY_COLUMNS)}")
            print(f"post_survey_fields_present={len(POST_SURVEY_COLUMNS) - len(missing_post)}/{len(POST_SURVEY_COLUMNS)}")
            if missing_pre:
                failures.append(f"Missing pre-survey fields on latest session: {missing_pre}")
            if missing_post:
                failures.append(f"Missing post-survey fields on latest session: {missing_post}")

            impression_count = scalar(connection, "SELECT COUNT(*) FROM impressions WHERE session_id = :session_id", {"session_id": session_id})
            event_count = scalar(connection, "SELECT COUNT(*) FROM events WHERE session_id = :session_id", {"session_id": session_id})
            print(f"impressions={impression_count}")
            print(f"events={event_count}")
            if impression_count < args.min_impressions:
                failures.append(f"Too few impressions for completed run: {impression_count} < {args.min_impressions}")
            if event_count == 0:
                failures.append("No events for completed run")

            missing_required_impression_fields = rows(
                connection,
                """
                SELECT
                  COUNT(*) FILTER (WHERE video_title IS NULL OR video_title = '') AS missing_video_title,
                  COUNT(*) FILTER (WHERE surface IS NULL OR surface = '') AS missing_surface,
                  COUNT(*) FILTER (WHERE click_from IS NULL OR click_from = '') AS missing_click_from,
                  COUNT(*) FILTER (WHERE video_id IS NULL OR video_id = '') AS missing_video_id,
                  COUNT(*) FILTER (WHERE user_id IS NULL OR user_id = '') AS missing_user_id,
                  COUNT(*) FILTER (WHERE session_id IS NULL OR session_id = '') AS missing_session_id,
                  COUNT(*) FILTER (WHERE exposure_id IS NULL OR exposure_id = '') AS missing_exposure_id,
                  COUNT(*) FILTER (WHERE client_log_id IS NULL OR client_log_id = '') AS missing_client_log_id,
                  COUNT(*) FILTER (WHERE client_event_at IS NULL) AS missing_client_event_at,
                  COUNT(*) FILTER (WHERE client_sequence_number IS NULL) AS missing_client_sequence_number
                FROM impressions
                WHERE session_id = :session_id
                """,
                {"session_id": session_id},
            )[0]
            bad_impression_fields = {k: v for k, v in missing_required_impression_fields.items() if int(v or 0) > 0}
            print(f"missing_required_impression_fields={bad_impression_fields}")
            if bad_impression_fields:
                failures.append(f"Some impressions miss required fields: {bad_impression_fields}")

            event_counts = Counter(
                {row["event_type"]: int(row["n"]) for row in rows(
                    connection,
                    "SELECT event_type, COUNT(*) AS n FROM events WHERE session_id = :session_id GROUP BY event_type",
                    {"session_id": session_id},
                )}
            )
            print(f"event_counts={dict(sorted(event_counts.items()))}")
            for required_event in ["watch_start", "exposure_end"]:
                if event_counts.get(required_event, 0) == 0:
                    failures.append(f"No {required_event} events for completed run")
            if args.require_clicks and event_counts.get("click", 0) == 0:
                failures.append("No click/swipe events for completed run")

            missing_required_event_fields = rows(
                connection,
                """
                SELECT
                  COUNT(*) FILTER (WHERE video_title IS NULL OR video_title = '') AS missing_video_title,
                  COUNT(*) FILTER (WHERE surface IS NULL OR surface = '') AS missing_surface,
                  COUNT(*) FILTER (WHERE click_from IS NULL OR click_from = '') AS missing_click_from,
                  COUNT(*) FILTER (WHERE exposure_id IS NULL OR exposure_id = '') AS missing_exposure_id,
                  COUNT(*) FILTER (WHERE client_log_id IS NULL OR client_log_id = '') AS missing_client_log_id,
                  COUNT(*) FILTER (WHERE client_event_at IS NULL) AS missing_client_event_at,
                  COUNT(*) FILTER (WHERE client_sequence_number IS NULL) AS missing_client_sequence_number
                FROM events
                WHERE session_id = :session_id
                """,
                {"session_id": session_id},
            )[0]
            bad_event_fields = {k: v for k, v in missing_required_event_fields.items() if int(v or 0) > 0}
            print(f"missing_required_event_fields={bad_event_fields}")
            if bad_event_fields:
                failures.append(f"Some events miss required fields: {bad_event_fields}")

            fake_timeout_events = scalar(
                connection,
                "SELECT COUNT(*) FROM events WHERE session_id = :session_id AND metadata_json LIKE '%shorts-reel-timeout%'",
                {"session_id": session_id},
            )
            print(f"fake_timeout_events={fake_timeout_events}")
            if fake_timeout_events:
                failures.append(f"Found obsolete timeout-generated playback events: {fake_timeout_events}")

            missing_actual_playing = scalar(
                connection,
                """
                SELECT COUNT(*) FROM events
                WHERE session_id = :session_id
                  AND event_type IN ('click', 'exposure_end')
                  AND metadata_json NOT LIKE '%actual_playing_ms%'
                """,
                {"session_id": session_id},
            )
            print(f"navigation_or_exposure_end_missing_actual_playing_ms={missing_actual_playing}")
            if missing_actual_playing:
                failures.append(f"Navigation/exposure-end events missing actual_playing_ms: {missing_actual_playing}")

            clicks_without_prior_impression = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM events e
                WHERE e.session_id = :session_id
                  AND e.event_type = 'click'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM impressions i
                    WHERE i.session_id = e.session_id
                      AND i.video_id = e.video_id
                      AND i.timestamp <= e.timestamp
                  )
                """,
                {"session_id": session_id},
            )
            print(f"clicks_without_prior_impression={clicks_without_prior_impression}")
            if clicks_without_prior_impression:
                failures.append(f"Clicks without prior impressions: {clicks_without_prior_impression}")

            pool_rows = rows(
                connection,
                "SELECT content_pool, COUNT(*) AS n FROM impressions WHERE session_id = :session_id GROUP BY content_pool ORDER BY content_pool",
                {"session_id": session_id},
            )
            pool_counts = {str(row["content_pool"]): int(row["n"]) for row in pool_rows}
            print(f"content_pool_counts={pool_counts}")
            condition = str(session.get("condition") or "")
            if condition == "control_recommendation" and pool_counts.get("problematic", 0) > 0:
                failures.append("Control session received problematic/manosphere impressions")
            if condition == "treatment_problematic_content" and pool_counts.get("problematic", 0) == 0:
                failures.append("Treatment session received no problematic/manosphere impressions")

            duplicate_impressions = scalar(
                connection,
                """
                SELECT COUNT(*) FROM (
                  SELECT exposure_id, COUNT(*) AS n
                  FROM impressions
                  WHERE session_id = :session_id
                    AND exposure_id IS NOT NULL
                  GROUP BY exposure_id
                  HAVING COUNT(*) > 3
                ) dup
                """,
                {"session_id": session_id},
            )
            print(f"excessive_duplicate_exposure_groups={duplicate_impressions}")
            if duplicate_impressions:
                failures.append("Some exposure_id impression groups are duplicated more than expected")

            if failures:
                print("=== PRELAUNCH AUDIT FAILED ===")
                for failure in failures:
                    print(f"ERROR: {failure}")
                return 1

            print("=== PRELAUNCH AUDIT PASSED ===")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
