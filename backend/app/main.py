from datetime import datetime, timedelta, timezone
from typing import Any
import json
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session
from . import models
from .backup_service import maybe_run_completion_backup, warn_backup_failure
from .database import Base, BehaviorSessionLocal, ContentSessionLocal, behavior_engine, content_engine, get_behavior_db, get_content_db
from .experiment import assign_condition, normalize_condition, normalize_pool_mode
from .logging_service import LoggingValidationError, log_event, log_impression, serialize_log_row
from .time_utils import ensure_utc_datetime, iso_utc
from .recommendation import available_topics, homepage_recommendations, prefer_real_youtube_rows, related_videos, score_video, servable_video_query, shorts_feed
from .schema_compat import ensure_experimental_schema
from .study_monitor import study_monitor_snapshot
from .schemas import EntrySurveyIn, EventIn, ImpressionIn, LegacyEventIn, SessionIn, StudyPostSurveyIn, StudyPreSurveyIn
from .seed import seed_database

Base.metadata.create_all(bind=content_engine, tables=[model.__table__ for model in models.CONTENT_MODELS])
Base.metadata.create_all(bind=behavior_engine, tables=[model.__table__ for model in models.BEHAVIOR_MODELS])
ensure_experimental_schema(content_engine)
ensure_experimental_schema(behavior_engine)

app = FastAPI(title="Experimental Video Platform API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_seed() -> None:
    db = ContentSessionLocal()
    try:
        # Keep ingested YouTube data authoritative. The seed fixture is only a
        # safety net for brand-new local databases with no videos.
        if db.query(models.Video).count() == 0:
            seed_database(db)
    finally:
        db.close()


def serialize_video(video: models.Video, rank: int | None = None) -> dict:
    payload = {
        "id": video.id,
        "title": video.title,
        "content_pool": video.content_pool,
        "channel": video.channel,
        "topic": video.topic,
        "thumbnail_url": video.thumbnail_url,
        "video_url": video.video_url,
        "duration_seconds": video.duration_seconds,
        "views": video.views,
        "popularity_score": video.popularity_score,
        "freshness_score": video.freshness_score,
        "is_short": video.is_short,
        "youtube_id": video.youtube_id,
        "source": video.source,
        "creator_slug": video.creator_slug,
        "review_group": video.review_group,
        "channel_id": video.channel_id,
        "ingest_source_type": video.ingest_source_type,
        "ingest_query": video.ingest_query,
        "short_confidence": video.short_confidence,
        "embeddable": video.embeddable,
        "embeddable_checked_at": video.embeddable_checked_at.isoformat() if getattr(video, "embeddable_checked_at", None) and hasattr(video.embeddable_checked_at, "isoformat") else None,
    }
    if rank is not None:
        payload["rank"] = rank
    return payload


def serialize_session(session: models.Session) -> dict:
    created_at = session.created_at or session.started_at
    return {
        "session_id": session.id,
        "id": session.id,
        "user_id": session.user_id,
        "condition": session.condition,
        "survey_completed": bool(getattr(session, "survey_completed", False)),
        "gender": session.gender,
        "age": session.age,
        "household_living_arrangement": session.household_living_arrangement,
        "education": session.education,
        "region_dk": session.region_dk,
        "left_right_orientation": session.left_right_orientation,
        "age_group": getattr(session, "age_group", None),
        "education_level": getattr(session, "education_level", None),
        "political_orientation": getattr(session, "political_orientation", None),
        "video_platform_use": getattr(session, "video_platform_use", None),
        "typical_video_platforms": getattr(session, "typical_video_platforms", None),
        "cohabitation_status": getattr(session, "cohabitation_status", None),
        "employment_status": getattr(session, "employment_status", None),
        "norstat_pid": getattr(session, "norstat_pid", None),
        "feminist_attitude": getattr(session, "feminist_attitude", None),
        "feminism_taken_too_far": getattr(session, "feminism_taken_too_far", None),
        "traditional_gender_attitude": getattr(session, "traditional_gender_attitude", None),
        "harder_to_be_a_man_today": getattr(session, "harder_to_be_a_man_today", None),
        "social_division": getattr(session, "social_division", None),
        "gender_conflict_exaggeration": getattr(session, "gender_conflict_exaggeration", None),
        "online_misinformation": getattr(session, "online_misinformation", None),
        "perceived_content_type": getattr(session, "perceived_content_type", None),
        "study_state": getattr(session, "study_state", "entry"),
        "reel_duration_seconds": getattr(session, "reel_duration_seconds", 240),
        "reel_started_at": iso_utc(getattr(session, "reel_started_at", None)),
        "reel_expires_at": iso_utc(getattr(session, "reel_expires_at", None)),
        "reel_completed_at": iso_utc(getattr(session, "reel_completed_at", None)),
        "post_survey_completed_at": iso_utc(getattr(session, "post_survey_completed_at", None)),
        "consent_status": getattr(session, "consent_status", None),
        "consented_at": iso_utc(getattr(session, "consented_at", None)),
        "screened_reason": getattr(session, "screened_reason", None),
        "screened_at": iso_utc(getattr(session, "screened_at", None)),
        "created_at": iso_utc(created_at),
    }


def resolve_video_reference(db: Session, video_id: str | None) -> models.Video | None:
    if not video_id:
        return None
    video = db.get(models.Video, video_id)
    if video:
        return video
    if video_id.startswith("v-"):
        return db.get(models.Video, video_id[2:])
    return None


def require_video_reference(db: Session, video_id: str | None) -> models.Video:
    video = resolve_video_reference(db, video_id)
    if not video:
        raise HTTPException(status_code=400, detail="video_id must reference an existing content video")
    return video


def get_or_create_user(db: Session, user_id: str | None) -> models.User | None:
    if not user_id:
        return None
    user = db.get(models.User, user_id)
    if user:
        return user
    user = models.User(id=user_id, username=user_id)
    db.add(user)
    db.flush()
    return user


def get_or_create_session(
    db: Session,
    session_id: str | None,
    condition: str | None,
    user_id: str | None = None,
) -> models.Session:
    if session_id:
        existing = db.get(models.Session, session_id)
        if existing:
            if user_id and existing.user_id is None:
                get_or_create_user(db, user_id)
                existing.user_id = user_id
                db.commit()
                db.refresh(existing)
            return existing
    assigned = assign_condition(condition)
    get_or_create_user(db, user_id)
    session = (
        models.Session(id=session_id, user_id=user_id, condition=assigned)
        if session_id
        else models.Session(user_id=user_id, condition=assigned)
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session




def latest_study_session_for_user(db: Session, *, user_id: str) -> models.Session | None:
    return (
        db.query(models.Session)
        .filter(models.Session.user_id == user_id)
        .filter(models.Session.study_state != "entry")
        .order_by(models.Session.created_at.desc())
        .first()
    )


def record_study_participation_status(
    db: Session,
    *,
    session_id: str,
    condition: str | None,
    user_id: str | None,
    consent_status: str,
    screened_reason: str | None = None,
    norstat_pid: str | None = None,
) -> models.Session:
    if consent_status not in {"accepted", "declined"}:
        raise HTTPException(status_code=400, detail="invalid consent_status")
    session = get_or_create_session(db, session_id, condition, user_id)
    now = datetime.now(timezone.utc)
    session.consent_status = consent_status
    if consent_status == "accepted" and session.consented_at is None:
        session.consented_at = now
    if screened_reason:
        session.screened_reason = screened_reason
        session.screened_at = now
    if norstat_pid:
        session.norstat_pid = norstat_pid
    db.commit()
    db.refresh(session)
    return session

def store_entry_survey(db: Session, session_id: str, payload: EntrySurveyIn) -> models.Session:
    session = get_or_create_session(db, session_id, payload.condition, payload.user_id)
    if payload.user_id and session.user_id is None:
        get_or_create_user(db, payload.user_id)
        session.user_id = payload.user_id
    session.survey_completed = True
    session.gender = payload.gender
    session.age = payload.age
    session.household_living_arrangement = payload.household_living_arrangement
    session.education = payload.education
    session.region_dk = payload.region_dk
    session.left_right_orientation = payload.left_right_orientation
    db.commit()
    db.refresh(session)
    return session


def store_study_pre_survey(db: Session, payload: StudyPreSurveyIn) -> models.Session:
    session = get_or_create_session(db, payload.session_id, payload.condition, payload.user_id)
    if payload.user_id and session.user_id is None:
        get_or_create_user(db, payload.user_id)
        session.user_id = payload.user_id
    session.survey_completed = True
    session.gender = payload.gender
    session.age_group = payload.age_group
    session.education_level = payload.education_level
    session.political_orientation = payload.political_orientation
    session.left_right_orientation = payload.political_orientation
    session.video_platform_use = payload.video_platform_use
    session.typical_video_platforms = json.dumps(payload.typical_video_platforms, ensure_ascii=False)
    session.cohabitation_status = payload.cohabitation_status
    session.employment_status = payload.employment_status
    session.norstat_pid = payload.norstat_pid
    db.commit()
    db.refresh(session)
    return session


def store_study_post_survey(db: Session, payload: StudyPostSurveyIn) -> models.Session:
    session = db.get(models.Session, payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    session.feminist_attitude = payload.feminist_attitude
    session.feminism_taken_too_far = payload.feminism_taken_too_far
    session.traditional_gender_attitude = payload.traditional_gender_attitude
    session.harder_to_be_a_man_today = payload.harder_to_be_a_man_today
    session.social_division = payload.social_division
    session.gender_conflict_exaggeration = payload.gender_conflict_exaggeration
    session.online_misinformation = payload.online_misinformation
    session.perceived_content_type = payload.perceived_content_type
    now = datetime.now(timezone.utc)
    session.study_state = "complete"
    if session.post_survey_completed_at is None:
        session.post_survey_completed_at = now
    db.commit()
    db.refresh(session)
    try:
        maybe_run_completion_backup(db)
    except Exception as exc:  # pragma: no cover
        warn_backup_failure(exc)
    return session


def prepare_study_session(
    db: Session,
    *,
    session_id: str,
    condition: str | None,
    user_id: str | None,
    reel_duration_seconds: int = 240,
) -> models.Session:
    session = get_or_create_session(db, session_id, condition, user_id)
    session.study_state = "assigned"
    session.reel_duration_seconds = max(1, int(reel_duration_seconds or 240))
    db.commit()
    db.refresh(session)
    return session


def activate_study_reel(db: Session, *, session_id: str) -> models.Session:
    session = db.get(models.Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.study_state == "complete":
        return session
    now = datetime.now(timezone.utc)
    reel_expires_at = ensure_utc_datetime(session.reel_expires_at)
    if reel_expires_at and reel_expires_at <= now:
        session.study_state = "reel_completed"
        if session.reel_completed_at is None:
            session.reel_completed_at = reel_expires_at
    else:
        if session.reel_started_at is None:
            session.reel_started_at = now
            session.reel_expires_at = now + timedelta(seconds=max(1, session.reel_duration_seconds or 240))
        session.study_state = "reel_active"
    db.commit()
    db.refresh(session)
    return session


def complete_study_reel(db: Session, *, session_id: str) -> models.Session:
    session = db.get(models.Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if session.study_state == "complete":
        return session
    now = datetime.now(timezone.utc)
    session.study_state = "reel_completed"
    if session.reel_started_at is None:
        session.reel_started_at = now
    if session.reel_expires_at is None:
        session.reel_expires_at = now
    if session.reel_completed_at is None:
        session.reel_completed_at = now
    db.commit()
    db.refresh(session)
    return session


def complete_study_post(db: Session, *, session_id: str) -> models.Session:
    session = db.get(models.Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    now = datetime.now(timezone.utc)
    session.study_state = "complete"
    if session.post_survey_completed_at is None:
        session.post_survey_completed_at = now
    db.commit()
    db.refresh(session)
    try:
        maybe_run_completion_backup(db)
    except Exception as exc:  # pragma: no cover - backup failures should not block participant completion
        warn_backup_failure(exc)
    return session


def apply_video_filters(query, surface: str | None, condition: str | None, content_pool: str | None):
    if surface == "shorts":
        query = query.filter(models.Video.is_short.is_(True))
    elif surface in {"recommendation", "related", "search"}:
        query = query.filter(models.Video.is_short.is_(False))
    pool_mode = normalize_pool_mode(content_pool, condition)
    if pool_mode != "mixed":
        query = query.filter(models.Video.content_pool == pool_mode)
    return query


@app.get("/")
def ok() -> dict:
    return {"ok": True, "service": "experimental-video-platform"}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "behavior_database": behavior_engine.dialect.name, "content_database": content_engine.dialect.name}


@app.get("/study/monitor")
def study_monitor(
    active_minutes: int = Query(default=5, ge=1, le=120),
    latest_limit: int = Query(default=15, ge=1, le=100),
    monitor_token: str | None = Header(default=None, alias="X-ViewTube-Monitor-Token"),
    db: Session = Depends(get_behavior_db),
) -> dict:
    expected = os.getenv("VIEWTUBE_MONITOR_TOKEN", "")
    if not expected or not monitor_token or not secrets.compare_digest(monitor_token, expected):
        raise HTTPException(status_code=404, detail="Not found")
    return study_monitor_snapshot(db, active_minutes=active_minutes, latest_limit=latest_limit)


@app.post("/bridge")
def bridge_action(payload: dict[str, Any]) -> dict:
    """Compatibility action endpoint for the Next.js server.

    Next.js historically spawned scripts/frontend_backend_bridge.py for each
    action.  UCloud production now keeps this FastAPI app warm and posts the
    same action payload here, avoiding per-request Python import cold starts.
    """

    action = payload.get("action")
    body = payload.get("payload") or {}
    if body is not None and not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    # Lazy import avoids circular import at module-load time: the bridge module
    # imports helpers from backend.app.main, so only import it after this app is
    # fully initialized and a request arrives.
    from scripts.frontend_backend_bridge import bridge_response  # noqa: WPS433

    return bridge_response(action if isinstance(action, str) else None, body)


@app.post("/sessions")
def create_session(payload: SessionIn | None = None, db: Session = Depends(get_behavior_db)) -> dict:
    condition = payload.condition if payload else None
    user_id = payload.user_id if payload else None
    return serialize_session(get_or_create_session(db, None, condition, user_id))


@app.get("/sessions/{session_id}")
def read_session(session_id: str, condition: str | None = None, user_id: str | None = None, db: Session = Depends(get_behavior_db)) -> dict:
    return serialize_session(get_or_create_session(db, session_id, condition, user_id))


@app.post("/sessions/{session_id}/survey")
def submit_entry_survey(session_id: str, payload: EntrySurveyIn, db: Session = Depends(get_behavior_db)) -> dict:
    return serialize_session(store_entry_survey(db, session_id, payload))


@app.get("/content-pools")
def content_pools(db: Session = Depends(get_content_db)) -> list[dict]:
    pools = db.query(models.ContentPool).filter(models.ContentPool.name.in_([ "safe", "problematic" ])).all()
    return [{"id": pool.id, "name": pool.name, "description": pool.description} for pool in pools]


@app.get("/videos")
def list_videos(
    surface: str | None = Query(default=None),
    condition: str | None = Query(default=None),
    content_pool: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    db: Session = Depends(get_content_db),
) -> list[dict]:
    query = db.query(models.Video)
    if surface:
        query = servable_video_query(query)
    query = apply_video_filters(query, surface, condition, content_pool)
    if topic and topic.lower() != "all":
        query = query.filter(models.Video.topic == topic)
    videos = query.all()
    return [serialize_video(video, index) for index, video in enumerate(videos, start=1)]


@app.get("/topics")
def topics(
    condition: str | None = Query(default=None),
    content_pool: str | None = Query(default=None),
    db: Session = Depends(get_content_db),
) -> list[str]:
    return available_topics(db, condition=normalize_condition(condition), content_pool=content_pool)


@app.get("/recommendations/homepage")
def homepage(
    session_id: str | None = None,
    user_id: str | None = None,
    condition: str | None = None,
    content_pool: str | None = None,
    topic: str | None = None,
    category: str | None = None,
    content_db: Session = Depends(get_content_db),
    behavior_db: Session = Depends(get_behavior_db),
) -> list[dict]:
    session = get_or_create_session(behavior_db, session_id, condition, user_id) if session_id else None
    effective_condition = session.condition if session else normalize_condition(condition)
    return [
        serialize_video(video, index)
        for index, video in enumerate(
            homepage_recommendations(
                content_db,
                condition=effective_condition,
                content_pool=content_pool,
                topic=topic or category,
                session_id=session.id if session else session_id,
            ),
            start=1,
        )
    ]


@app.get("/videos/{video_id}")
def get_video(video_id: str, db: Session = Depends(get_content_db)) -> dict:
    video = db.get(models.Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    return serialize_video(video)


@app.get("/videos/{video_id}/related")
def related(
    video_id: str,
    session_id: str | None = None,
    user_id: str | None = None,
    condition: str | None = None,
    content_pool: str | None = None,
    content_db: Session = Depends(get_content_db),
    behavior_db: Session = Depends(get_behavior_db),
) -> list[dict]:
    video = content_db.get(models.Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="video not found")
    session = get_or_create_session(behavior_db, session_id, condition, user_id) if session_id else None
    effective_condition = session.condition if session else normalize_condition(condition)
    return [
        serialize_video(item, index)
        for index, item in enumerate(
            related_videos(
                content_db,
                video,
                condition=effective_condition,
                content_pool=content_pool,
                session_id=session.id if session else session_id,
            ),
            start=1,
        )
    ]


@app.get("/shorts")
def shorts(
    session_id: str | None = None,
    user_id: str | None = None,
    condition: str | None = None,
    content_pool: str | None = None,
    content_db: Session = Depends(get_content_db),
    behavior_db: Session = Depends(get_behavior_db),
) -> list[dict]:
    session = get_or_create_session(behavior_db, session_id, condition, user_id) if session_id else None
    effective_condition = session.condition if session else normalize_condition(condition)
    return [
        serialize_video(video, index)
        for index, video in enumerate(
            shorts_feed(content_db, condition=effective_condition, content_pool=content_pool, session_id=session.id if session else session_id),
            start=1,
        )
    ]


@app.get("/search")
def search(
    q: str = Query(default=""),
    session_id: str | None = None,
    user_id: str | None = None,
    condition: str | None = None,
    content_pool: str | None = None,
    content_db: Session = Depends(get_content_db),
    behavior_db: Session = Depends(get_behavior_db),
) -> dict:
    normalized = q.strip().lower()
    session = get_or_create_session(behavior_db, session_id, condition, user_id) if session_id else None
    effective_condition = session.condition if session else normalize_condition(condition)
    query = servable_video_query(content_db.query(models.Video)).filter(models.Video.is_short.is_(False))
    candidates = prefer_real_youtube_rows(apply_video_filters(query, "search", effective_condition, content_pool).all())
    ranked_candidates = sorted(
        candidates,
        key=lambda video: (score_video(video), video.views or 0, video.title.lower(), video.id),
        reverse=True,
    )
    if normalized:
        results = [
            video
            for video in ranked_candidates
            if normalized in video.title.lower()
            or normalized in video.channel.lower()
            or normalized in video.topic.lower()
        ]
    else:
        results = ranked_candidates
    behavior_db.add(
        models.SearchQuery(
            user_id=user_id or (session.user_id if session else None),
            session_id=session.id if session else session_id,
            condition=effective_condition,
            gender=session.gender if session else None,
            query=q,
            result_count=len(results),
        )
    )
    behavior_db.commit()
    return {"query": q, "results": [serialize_video(video, index) for index, video in enumerate(results, start=1)]}


@app.post("/impressions")
def create_impression(
    payload: ImpressionIn,
    behavior_db: Session = Depends(get_behavior_db),
    content_db: Session = Depends(get_content_db),
) -> dict:
    video = require_video_reference(content_db, payload.video_id)
    try:
        impression = log_impression(
            behavior_db,
            **(payload.model_dump() | {"video_id": video.id, "video_title": video.title}),
        )
    except LoggingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_log_row(impression)


@app.post("/events")
def create_event(
    payload: EventIn,
    behavior_db: Session = Depends(get_behavior_db),
    content_db: Session = Depends(get_content_db),
) -> dict:
    video = require_video_reference(content_db, payload.video_id)
    try:
        event = log_event(
            behavior_db,
            **(payload.model_dump() | {"video_id": video.id, "video_title": video.title}),
        )
    except LoggingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_log_row(event) | {"event_type": event.event_type}


@app.post("/event")
def create_legacy_event(
    payload: dict[str, Any],
    behavior_db: Session = Depends(get_behavior_db),
    content_db: Session = Depends(get_content_db),
) -> dict:
    """Compatibility endpoint for the experimental event contract.

    It accepts a compact event payload, creates a session when omitted, and logs
    an impression before click events so the strict ordering rule is preserved.
    New clients should use /impressions and /events directly.
    """
    try:
        compact = LegacyEventIn.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_id = compact.session_id
    if not session_id:
        session = get_or_create_session(behavior_db, None, compact.condition, compact.user_id)
        session_id = session.id
    video = require_video_reference(content_db, compact.video_id)
    surface = compact.surface or compact.click_from
    event_payload = {
        "video_id": video.id,
        "video_title": video.title,
        "surface": surface,
        "click_from": compact.click_from,
        "rank": compact.rank,
        "session_id": session_id,
        "condition": compact.condition,
        "content_pool": compact.content_pool,
        "user_id": compact.user_id,
        "gender": compact.gender,
    }
    try:
        if compact.event_type == "click":
            log_impression(behavior_db, **event_payload)
        event = log_event(behavior_db, **event_payload, event_type=compact.event_type, metadata=compact.metadata)
    except LoggingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_log_row(event) | {"event_type": event.event_type}


@app.get("/logs")
def logs(db: Session = Depends(get_behavior_db)) -> dict:
    impressions = db.query(models.Impression).order_by(models.Impression.timestamp.desc()).limit(50).all()
    events = db.query(models.Event).order_by(models.Event.timestamp.desc()).limit(50).all()
    return {
        "impressions": [serialize_log_row(row) for row in impressions],
        "events": [serialize_log_row(row) | {"event_type": row.event_type} for row in events],
    }
