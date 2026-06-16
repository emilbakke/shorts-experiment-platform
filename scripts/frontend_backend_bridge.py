#!/usr/bin/env python3
"""Small Next.js-to-backend bridge for DB-backed video data and logs.

The frontend test server does not launch uvicorn, but the platform data and
logging contracts live in the FastAPI/SQLAlchemy backend. This bridge lets
Next.js API routes and server components call the backend modules directly
against the configured content and behavior SQLite databases without recreating
schema or touching the ingested videos table.
"""

from __future__ import annotations

import json
import os
import sys
import csv
from pathlib import Path
from typing import Any
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
PY_DEPS = REPO_ROOT / f".python_deps_{sys.version_info.major}{sys.version_info.minor}"
LEGACY_PY_DEPS = REPO_ROOT / ".python_deps"
LEGACY_DB_PATH = REPO_ROOT / "backend" / "app.db"

for deps_path in (LEGACY_PY_DEPS, PY_DEPS):
    if str(deps_path) not in sys.path:
        sys.path.insert(0, str(deps_path))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.local_db_defaults import default_database_urls  # noqa: E402

default_content_url, default_behavior_url, default_database_url = default_database_urls()
os.environ.setdefault("DATABASE_URL", default_database_url)
os.environ.setdefault("CONTENT_DATABASE_URL", default_content_url if "DATABASE_URL" not in os.environ else os.environ["DATABASE_URL"])
os.environ.setdefault("BEHAVIOR_DATABASE_URL", default_behavior_url if "DATABASE_URL" not in os.environ else os.environ["DATABASE_URL"])

from pydantic import ValidationError  # noqa: E402

from backend.app import models  # noqa: E402
from backend.app.database import BehaviorSessionLocal, ContentSessionLocal  # noqa: E402
from backend.app.experiment import normalize_condition  # noqa: E402
from backend.app.logging_service import (  # noqa: E402
    LoggingValidationError,
    log_event,
    log_impression,
    serialize_log_row,
)
from backend.app.time_utils import iso_utc  # noqa: E402
from backend.app.main import (  # noqa: E402
    activate_study_reel,
    complete_study_post,
    complete_study_reel,
    get_or_create_session,
    latest_study_session_for_user,
    prepare_study_session,
    record_study_participation_status,
    serialize_session,
    serialize_video,
    store_entry_survey,
    store_study_post_survey,
    store_study_pre_survey,
)
from backend.app.recommendation import available_topics, homepage_recommendations, related_videos, servable_video_query, shorts_feed  # noqa: E402
from backend.app.schemas import EntrySurveyIn, EventIn, ImpressionIn, SessionIn, StudyPostSurveyIn, StudyPreSurveyIn  # noqa: E402
from backend.app.seed import seed_database  # noqa: E402


DEMO_ALIASES = {
    "v1": "Neon City Walkthrough in 4K",
    "v2": "How Recommendation Systems Rank Videos",
    "v3": "Street Food Tour: Night Market Classics",
    "v4": "Build a Cozy Desk Setup from Scratch",
    "v5": "Morning Focus Music for Deep Work",
    "v6": "Beginner Camera Moves That Feel Cinematic",
    "v7": "Tiny Apartment Makeover Timelapse",
    "v8": "One-Day Train Trip Along the Coast",
    "s1": "60-Second Pasta Trick",
    "s2": "Desk Cable Cleanup Hack",
    "s3": "City Sunrise Hyperlapse",
    "s4": "AI Term Explained Fast",
}

STUDY_MEDIA_ROOT = REPO_ROOT / "study_media"


class BridgeResult(Exception):
    """Internal control-flow exception for bridge responses.

    The original bridge was a CLI-only script that printed a JSON response and
    exited.  The persistent FastAPI process reuses the same action dispatcher,
    so responses need to be returnable without terminating the uvicorn worker.
    """

    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(response.get("error") or "bridge result")
        self.response = response


def fail(message: str, status: int = 400) -> None:
    raise BridgeResult({"ok": False, "status": status, "error": message})


def ok(data: Any, status: int = 200) -> None:
    raise BridgeResult({"ok": True, "status": status, "data": data})


def ensure_video_data(content_db) -> None:
    if content_db.query(models.Video).count() == 0:
        seed_database(content_db)


def with_route_id(video_payload: dict[str, Any]) -> dict[str, Any]:
    # Keep logged video_id as the real database id while making watch URLs
    # stable and compatible with existing /watch/v* tests.
    return video_payload | {"route_id": f"v-{video_payload['id']}"}


def serialize_ranked(videos: list[models.Video]) -> list[dict[str, Any]]:
    return [with_route_id(serialize_video(video, index)) for index, video in enumerate(videos, start=1)]


def _study_media_metadata() -> dict[str, dict[str, str]]:
    """Return optional CSV metadata keyed by local YouTube/video id."""
    rows: dict[str, dict[str, str]] = {}
    for csv_path in STUDY_MEDIA_ROOT.rglob("*.csv"):
        try:
            with csv_path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    video_id = (row.get("video_id") or "").strip()
                    if video_id:
                        rows[video_id] = row
        except OSError:
            continue
    return rows


def _study_sequence_manifest() -> dict[str, list[dict[str, str]]]:
    manifest_path = STUDY_MEDIA_ROOT / "sequence_manifest.csv"
    if not manifest_path.exists():
        return {}
    rows_by_arm: dict[str, list[dict[str, str]]] = {"control": [], "treatment": []}
    with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            arm = (row.get("arm") or "").strip()
            if arm not in rows_by_arm:
                continue
            rows_by_arm[arm].append(row)
    for rows in rows_by_arm.values():
        rows.sort(key=lambda row: int(row.get("order") or 0))
    return rows_by_arm


def _mp4s_in(path: Path) -> list[Path]:
    return sorted([candidate for candidate in path.glob("*.mp4") if candidate.is_file()], key=lambda item: item.name)


def _study_media_files_for_arm(arm: str) -> list[Path]:
    """Resolve fixed study files for an arm, with a toy-data fallback.

    Production can provide study_media/control and study_media/treatment.
    The current toy dataset only has study_media/regular/selected, so split
    that fixed sorted list into two deterministic arms until final folders
    are available.
    """
    explicit_files: list[Path] = []
    for candidate_dir in (STUDY_MEDIA_ROOT / arm / "selected", STUDY_MEDIA_ROOT / arm):
        if candidate_dir.is_dir():
            explicit_files = _mp4s_in(candidate_dir)
            if explicit_files:
                return explicit_files

    selected_dir = STUDY_MEDIA_ROOT / "regular" / "selected"
    fallback_files = _mp4s_in(selected_dir) if selected_dir.is_dir() else []
    if not fallback_files:
        regular_dir = STUDY_MEDIA_ROOT / "regular"
        fallback_files = sorted(regular_dir.rglob("*.mp4"), key=lambda item: item.relative_to(regular_dir).as_posix()) if regular_dir.is_dir() else []
    if not fallback_files:
        return []

    split_at = max(1, len(fallback_files) // 2)
    return fallback_files[:split_at] if arm == "control" else fallback_files[split_at:]


def _study_arm_for_condition(condition: str) -> str:
    return "treatment" if normalize_condition(condition) == "treatment_problematic_content" else "control"


def _relative_study_media_url(path: Path) -> str:
    relative = path.relative_to(STUDY_MEDIA_ROOT).as_posix()
    return f"/api/study/media/{quote(relative)}"


def study_local_shorts(content_db, behavior_db, *, session_id: str | None, condition: str | None) -> list[dict[str, Any]]:
    session = behavior_db.get(models.Session, session_id) if session_id else None
    effective_condition = session.condition if session else normalize_condition(condition)
    arm = _study_arm_for_condition(effective_condition)
    manifest = _study_sequence_manifest()
    if manifest.get(arm):
        return _study_manifest_shorts(content_db, manifest[arm])

    files = _study_media_files_for_arm(arm)
    if not files:
        return serialize_ranked(shorts_feed(content_db, condition=effective_condition, session_id=session_id))

    metadata_by_id = _study_media_metadata()
    content_pool = "problematic" if arm == "treatment" else "safe"
    pool = content_db.query(models.ContentPool).filter(models.ContentPool.name == content_pool).first()
    videos: list[models.Video] = []

    for index, media_path in enumerate(files, start=1):
        video_key = media_path.stem
        row = metadata_by_id.get(video_key, {})
        title = (
            row.get("cleaned_title")
            or row.get("metadata_title")
            or row.get("watched_title")
            or f"Studievideo {index}"
        )
        channel = row.get("channel") or row.get("uploader") or "Studievideo"
        try:
            duration_seconds = int(float(row.get("duration_sec") or row.get("duration_raw") or 0))
        except ValueError:
            duration_seconds = 0
        video_id = f"study-local-{arm}-{index:03d}-{video_key}"
        video = content_db.get(models.Video, video_id)
        if video is None:
            video = models.Video(id=video_id)
            content_db.add(video)
        video.content_pool_id = pool.id if pool else None
        video.content_pool = content_pool
        video.title = title
        video.channel = channel
        video.topic = "Shorts"
        video.thumbnail_url = f"gradient://study-{arm}-{index}"
        video.video_url = _relative_study_media_url(media_path)
        video.duration_seconds = duration_seconds
        video.views = int(float(row.get("metadata_view_count") or row.get("total_views") or 0))
        video.popularity_score = max(0, 1000 - index)
        video.freshness_score = 0
        video.is_short = True
        video.youtube_id = None
        video.source = "local"
        video.creator_slug = channel.lower().replace(" ", "-")[:80]
        video.review_group = f"study_{arm}"
        video.ingest_source_type = "study_media"
        video.short_confidence = "local_study_sequence"
        video.embeddable = True
        videos.append(video)

    content_db.commit()
    return serialize_ranked(videos)


def _study_manifest_shorts(content_db, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    videos: list[models.Video] = []
    for row in rows:
        arm = row.get("arm") or "control"
        order = int(row.get("order") or len(videos) + 1)
        raw_video_id = row.get("video_id") or Path(row.get("filename") or f"study-{order}").stem
        video_id = f"study-local-{arm}-{order:03d}-{raw_video_id}"
        video = content_db.get(models.Video, video_id)
        if video is None:
            video = models.Video(id=video_id)
            content_db.add(video)
        content_pool = row.get("content_pool") or ("problematic" if row.get("is_manosphere") == "True" else "safe")
        pool = content_db.query(models.ContentPool).filter(models.ContentPool.name == content_pool).first()
        video.content_pool_id = pool.id if pool else None
        video.content_pool = content_pool
        video.title = row.get("title") or raw_video_id
        video.channel = row.get("channel") or "Studievideo"
        video.topic = "Shorts"
        video.thumbnail_url = f"gradient://study-{arm}-{order}"
        video.video_url = f"/api/study/media/{quote(row.get('served_path') or row.get('filename') or '')}"
        try:
            video.duration_seconds = int(float(row.get("duration_sec") or 0))
        except ValueError:
            video.duration_seconds = 0
        video.views = 0
        video.popularity_score = max(0, 1000 - order)
        video.freshness_score = 0
        video.is_short = True
        video.youtube_id = None
        video.source = "local"
        video.creator_slug = video.channel.lower().replace(" ", "-")[:80]
        video.review_group = f"study_{arm}"
        video.ingest_source_type = "study_media_manifest"
        video.short_confidence = "local_study_sequence"
        video.embeddable = True
        videos.append(video)

    content_db.commit()
    return serialize_ranked(videos)


def resolve_video(content_db, video_id: str) -> models.Video | None:
    video = content_db.get(models.Video, video_id[2:]) if video_id.startswith("v-") else content_db.get(models.Video, video_id)
    if video:
        return video
    alias_title = DEMO_ALIASES.get(video_id)
    if alias_title:
        return content_db.query(models.Video).filter(models.Video.title == alias_title).first()
    return None


def canonical_video(content_db, video_id: str, status: int = 400) -> models.Video:
    video = content_db.get(models.Video, video_id[2:]) if video_id.startswith("v-") else content_db.get(models.Video, video_id)
    if video:
        return video
    alias_title = DEMO_ALIASES.get(video_id)
    if alias_title:
        alias = content_db.query(models.Video).filter(models.Video.title == alias_title).first()
        if alias:
            return alias
    fail("video_id must reference an existing content video", status=status)


def search_videos(content_db, query: str, condition: str | None, content_pool: str | None) -> list[models.Video]:
    normalized = (query or "").strip().lower()
    effective_condition = normalize_condition(condition)
    candidates = homepage_recommendations(content_db, limit=10_000, condition=effective_condition, content_pool=content_pool)
    if not normalized:
        return candidates
    return [
        video
        for video in candidates
        if normalized in video.title.lower()
        or normalized in video.channel.lower()
        or normalized in video.topic.lower()
    ]


def logs_payload(behavior_db) -> dict[str, Any]:
    impressions = list(reversed(behavior_db.query(models.Impression).order_by(models.Impression.timestamp.desc()).limit(500).all()))
    events = list(reversed(behavior_db.query(models.Event).order_by(models.Event.timestamp.desc()).limit(500).all()))
    searches = list(reversed(behavior_db.query(models.SearchQuery).order_by(models.SearchQuery.timestamp.desc()).limit(200).all()))
    sessions = list(reversed(behavior_db.query(models.Session).order_by(models.Session.started_at.desc()).limit(200).all()))
    return {
        "impressions": [serialize_log_row(row) for row in impressions],
        "events": [serialize_log_row(row) | {"event_type": row.event_type} for row in events],
        "searches": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "session_id": row.session_id,
                "condition": row.condition,
                "query": row.query,
                "result_count": row.result_count,
                "timestamp": iso_utc(row.timestamp),
            }
            for row in searches
        ],
        "sessions": [serialize_session(row) for row in sessions],
    }


def reset_logs(behavior_db) -> dict[str, Any]:
    behavior_db.query(models.Event).delete()
    behavior_db.query(models.Impression).delete()
    behavior_db.query(models.SearchQuery).delete()
    behavior_db.query(models.Session).delete()
    behavior_db.commit()
    return logs_payload(behavior_db)


def run_action(action: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    content_db = ContentSessionLocal()
    behavior_db = BehaviorSessionLocal()
    try:
        ensure_video_data(content_db)

        if action == "homepage":
            ok(
                serialize_ranked(
                    homepage_recommendations(
                        content_db,
                        condition=payload.get("condition"),
                        content_pool=payload.get("content_pool"),
                        topic=payload.get("topic") or payload.get("category"),
                        session_id=payload.get("session_id"),
                    )
                )
            )

        if action == "homepage_bundle":
            condition = payload.get("condition")
            content_pool = payload.get("content_pool")
            session_id = payload.get("session_id")
            category = payload.get("topic") or payload.get("category")
            ok(
                {
                    "shorts": serialize_ranked(
                        shorts_feed(
                            content_db,
                            condition=condition,
                            content_pool=content_pool,
                            session_id=session_id,
                        )
                    ),
                    "videos": serialize_ranked(
                        homepage_recommendations(
                            content_db,
                            condition=condition,
                            content_pool=content_pool,
                            topic=category,
                            session_id=session_id,
                        )
                    ),
                    "topics": available_topics(content_db, condition=condition, content_pool=content_pool),
                }
            )

        if action == "all_videos":
            videos = servable_video_query(content_db.query(models.Video)).all()
            ok([with_route_id(serialize_video(video)) for video in videos])

        if action == "topics":
            ok(available_topics(content_db, condition=payload.get("condition"), content_pool=payload.get("content_pool")))

        if action == "shorts":
            ok(
                serialize_ranked(
                    shorts_feed(
                        content_db,
                        condition=payload.get("condition"),
                        content_pool=payload.get("content_pool"),
                        session_id=payload.get("session_id"),
                    )
                )
            )

        if action == "study_shorts":
            ok(study_local_shorts(content_db, behavior_db, session_id=payload.get("session_id"), condition=payload.get("condition")))

        if action == "video":
            video = resolve_video(content_db, payload.get("video_id", ""))
            ok(with_route_id(serialize_video(video)) if video else None, status=200 if video else 404)

        if action == "watch":
            video = resolve_video(content_db, payload.get("video_id", ""))
            if not video:
                ok({"video": None, "related": []}, status=404)
            ok(
                {
                    "video": with_route_id(serialize_video(video)),
                    "related": serialize_ranked(
                        related_videos(
                            content_db,
                            video,
                            condition=payload.get("condition"),
                            content_pool=payload.get("content_pool"),
                            session_id=payload.get("session_id"),
                        )
                    ),
                }
            )

        if action == "related":
            video = resolve_video(content_db, payload.get("video_id", ""))
            if not video:
                ok([], status=404)
            ok(
                serialize_ranked(
                    related_videos(
                        content_db,
                        video,
                        condition=payload.get("condition"),
                        content_pool=payload.get("content_pool"),
                        session_id=payload.get("session_id"),
                    )
                )
            )

        if action == "search_results":
            condition = normalize_condition(payload.get("condition"))
            results = search_videos(content_db, payload.get("q", ""), condition, payload.get("content_pool"))
            ok({"query": payload.get("q", ""), "condition": condition, "results": serialize_ranked(results)})

        if action == "search":
            condition = normalize_condition(payload.get("condition"))
            results = search_videos(content_db, payload.get("q", ""), condition, payload.get("content_pool"))
            session_id = payload.get("session_id")
            user_id = payload.get("user_id")
            session = None
            if session_id:
                session = get_or_create_session(behavior_db, session_id, condition, user_id)
                user_id = user_id or session.user_id
            behavior_db.add(
                models.SearchQuery(
                    user_id=user_id,
                    session_id=session_id,
                    condition=condition,
                    gender=session.gender if session else None,
                    query=payload.get("q", ""),
                    result_count=len(results),
                )
            )
            behavior_db.commit()
            ok({"query": payload.get("q", ""), "condition": condition, "results": serialize_ranked(results)})

        if action == "session":
            body = SessionIn.model_validate(payload)
            ok(serialize_session(get_or_create_session(behavior_db, None, body.condition, body.user_id)))

        if action == "ensure_session":
            body = SessionIn.model_validate(payload)
            session = get_or_create_session(behavior_db, payload.get("session_id"), body.condition, body.user_id)
            if body.reel_duration_seconds and body.reel_duration_seconds > 0 and getattr(session, "reel_started_at", None) is None:
                session.reel_duration_seconds = body.reel_duration_seconds
                behavior_db.commit()
                behavior_db.refresh(session)
            ok(serialize_session(session))

        if action == "latest_study_session":
            user_id = payload.get("user_id")
            if not user_id:
                fail("user_id is required", status=400)
            session = latest_study_session_for_user(behavior_db, user_id=user_id)
            ok(serialize_session(session) if session else None)

        if action == "study_prepare":
            body = SessionIn.model_validate(payload)
            session_id = payload.get("session_id")
            if not session_id:
                fail("session_id is required", status=400)
            ok(
                serialize_session(
                    prepare_study_session(
                        behavior_db,
                        session_id=session_id,
                        condition=body.condition,
                        user_id=body.user_id,
                        reel_duration_seconds=body.reel_duration_seconds or 240,
                    )
                )
            )

        if action == "study_participation_status":
            session_id = payload.get("session_id")
            user_id = payload.get("user_id")
            consent_status = payload.get("consent_status")
            if not session_id or not user_id or not consent_status:
                fail("session_id, user_id, and consent_status are required", status=400)
            ok(serialize_session(record_study_participation_status(
                behavior_db,
                session_id=session_id,
                condition=payload.get("condition"),
                user_id=user_id,
                consent_status=consent_status,
                screened_reason=payload.get("screened_reason"),
                norstat_pid=payload.get("norstat_pid"),
            )))

        if action == "study_pre_survey":
            body = StudyPreSurveyIn.model_validate(payload)
            ok(serialize_session(store_study_pre_survey(behavior_db, body)))

        if action == "study_post_survey":
            body = StudyPostSurveyIn.model_validate(payload)
            ok(serialize_session(store_study_post_survey(behavior_db, body)))

        if action == "study_reel_activate":
            session_id = payload.get("session_id")
            if not session_id:
                fail("session_id is required", status=400)
            ok(serialize_session(activate_study_reel(behavior_db, session_id=session_id)))

        if action == "study_reel_complete":
            session_id = payload.get("session_id")
            if not session_id:
                fail("session_id is required", status=400)
            ok(serialize_session(complete_study_reel(behavior_db, session_id=session_id)))

        if action == "study_complete":
            session_id = payload.get("session_id")
            if not session_id:
                fail("session_id is required", status=400)
            ok(serialize_session(complete_study_post(behavior_db, session_id=session_id)))

        if action == "survey":
            session_id = payload.get("session_id")
            if not session_id:
                fail("session_id is required", status=400)
            body = EntrySurveyIn.model_validate(payload)
            ok(serialize_session(store_entry_survey(behavior_db, session_id, body)))

        if action == "impression":
            body = ImpressionIn.model_validate(payload)
            video = canonical_video(content_db, body.video_id)
            ok(
                serialize_log_row(
                    log_impression(
                        behavior_db,
                        **(body.model_dump() | {"video_id": video.id, "video_title": video.title}),
                    )
                )
            )

        if action == "event":
            body = EventIn.model_validate(payload)
            video = canonical_video(content_db, body.video_id)
            event = log_event(
                behavior_db,
                **(body.model_dump() | {"video_id": video.id, "video_title": video.title}),
            )
            ok(serialize_log_row(event) | {"event_type": event.event_type})

        if action == "logs":
            ok(logs_payload(behavior_db))

        if action == "reset_logs":
            ok(reset_logs(behavior_db))

        fail(f"unknown action: {action}", status=404)
    except ValidationError as exc:
        fail(str(exc), status=400)
    except LoggingValidationError as exc:
        fail(str(exc), status=400)
    finally:
        behavior_db.close()
        content_db.close()


def bridge_response(action: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return run_action(action, payload)
    except BridgeResult as result:
        return result.response
    except Exception as exc:  # pragma: no cover - defensive API boundary
        status = int(getattr(exc, "status_code", 500) or 500)
        detail = getattr(exc, "detail", None)
        message = str(detail or exc)
        return {"ok": False, "status": status, "error": message}


def main() -> None:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        response = {"ok": False, "status": 400, "error": f"invalid json: {exc}"}
    else:
        response = bridge_response(request.get("action"), request.get("payload") or {})
    print(json.dumps(response, default=str))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
