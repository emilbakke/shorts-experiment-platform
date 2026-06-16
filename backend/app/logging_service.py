import json
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from . import models
from .experiment import validate_condition, validate_content_pool
from .time_utils import iso_utc

ALLOWED_SURFACES = {"search", "recommendation", "related", "shorts"}
CLICK_EVENTS = {"click"}
PLAYER_EVENTS = {"watch_start", "progress", "complete"}
ATTENTION_EVENTS = {"visibility_hidden", "visibility_visible", "window_blur", "window_focus"}
PLAYBACK_DIAGNOSTIC_EVENTS = {"playback_waiting", "playback_stalled", "playback_pause", "playback_error", "exposure_end"}


class LoggingValidationError(ValueError):
    pass


def _validate_common(
    video_id: str,
    video_title: str,
    surface: str,
    rank: int,
    session_id: str,
    condition: str,
    content_pool: str,
) -> None:
    if not session_id:
        raise LoggingValidationError("session_id is required")
    if not video_id:
        raise LoggingValidationError("video_id is required")
    if not video_title:
        raise LoggingValidationError("video_title is required")
    if surface not in ALLOWED_SURFACES:
        raise LoggingValidationError("surface must be search, recommendation, related, or shorts")
    if rank < 0:
        raise LoggingValidationError("rank must be non-negative")
    try:
        validate_condition(condition)
        validate_content_pool(content_pool)
    except ValueError as exc:
        raise LoggingValidationError(str(exc)) from exc


def _ensure_user(db: Session, user_id: str) -> None:
    if not user_id:
        raise LoggingValidationError("user_id is required")
    if db.get(models.User, user_id) is None:
        db.add(models.User(id=user_id, username=user_id))
        db.flush()


def _ensure_session(db: Session, session_id: str, condition: str, user_id: str | None = None) -> tuple[str, models.Session]:
    session = db.get(models.Session, session_id)
    if session is None:
        resolved_user_id = user_id or session_id
        _ensure_user(db, resolved_user_id)
        session = models.Session(id=session_id, user_id=resolved_user_id, condition=condition)
        db.add(session)
        db.flush()
        return resolved_user_id, session
    elif session.condition != condition:
        raise LoggingValidationError("condition must match the session assignment")
    resolved_user_id = user_id or session.user_id or session_id
    _ensure_user(db, resolved_user_id)
    if session.user_id is None:
        session.user_id = resolved_user_id
        db.flush()
    elif session.user_id != resolved_user_id:
        raise LoggingValidationError("user_id must match the session assignment")
    return resolved_user_id, session


def _resolve_gender(session: models.Session, gender: str | None) -> str:
    value = (gender or session.gender or "").strip()
    return value or "unspecified"


def log_impression(
    db: Session,
    *,
    video_id: str,
    video_title: str,
    surface: str,
    rank: int,
    session_id: str,
    condition: str,
    content_pool: str,
    click_from: str,
    user_id: str | None = None,
    gender: str | None = None,
    exposure_id: str | None = None,
    client_log_id: str | None = None,
    client_event_at: datetime | None = None,
    client_sequence_number: int | None = None,
) -> models.Impression:
    _validate_common(video_id, video_title, surface, rank, session_id, condition, content_pool)
    if click_from not in ALLOWED_SURFACES:
        raise LoggingValidationError("click_from is required and must be search, recommendation, related, or shorts")
    if client_log_id:
        existing = db.query(models.Impression).filter(models.Impression.client_log_id == client_log_id).first()
        if existing is not None:
            return existing
    resolved_user_id, session = _ensure_session(db, session_id, condition, user_id)
    resolved_gender = _resolve_gender(session, gender)

    impression = models.Impression(
        user_id=resolved_user_id,
        session_id=session_id,
        condition=condition,
        video_id=video_id,
        video_title=video_title,
        surface=surface,
        click_from=click_from,
        content_pool=content_pool,
        gender=resolved_gender,
        rank=rank,
        exposure_id=exposure_id,
        client_log_id=client_log_id,
        client_event_at=client_event_at,
        client_sequence_number=client_sequence_number,
    )
    db.add(impression)
    db.commit()
    db.refresh(impression)
    return impression


def _has_prior_impression(db: Session, *, video_id: str, session_id: str | None, surface: str) -> bool:
    query = db.query(models.Impression).filter(
        models.Impression.video_id == video_id,
        models.Impression.surface == surface,
    )
    if session_id:
        query = query.filter(models.Impression.session_id == session_id)
    return db.query(query.exists()).scalar() is True


def log_event(
    db: Session,
    *,
    video_id: str,
    video_title: str,
    surface: str,
    click_from: str,
    rank: int,
    event_type: str,
    session_id: str,
    condition: str,
    content_pool: str,
    user_id: str | None = None,
    gender: str | None = None,
    metadata: dict[str, Any] | None = None,
    exposure_id: str | None = None,
    client_log_id: str | None = None,
    client_event_at: datetime | None = None,
    client_sequence_number: int | None = None,
) -> models.Event:
    _validate_common(video_id, video_title, surface, rank, session_id, condition, content_pool)
    if click_from not in ALLOWED_SURFACES:
        raise LoggingValidationError("click_from is required and must be search, recommendation, related, or shorts")
    if event_type not in CLICK_EVENTS | PLAYER_EVENTS | ATTENTION_EVENTS | PLAYBACK_DIAGNOSTIC_EVENTS:
        raise LoggingValidationError("event_type must be a supported interaction, playback, or attention event")
    if client_log_id:
        existing = db.query(models.Event).filter(models.Event.client_log_id == client_log_id).first()
        if existing is not None:
            return existing
    if event_type in CLICK_EVENTS and not _has_prior_impression(
        db, video_id=video_id, session_id=session_id, surface=surface
    ):
        raise LoggingValidationError("impression must be logged before click")
    resolved_user_id, session = _ensure_session(db, session_id, condition, user_id)
    resolved_gender = _resolve_gender(session, gender)

    event = models.Event(
        user_id=resolved_user_id,
        session_id=session_id,
        condition=condition,
        video_id=video_id,
        video_title=video_title,
        event_type=event_type,
        surface=surface,
        click_from=click_from,
        content_pool=content_pool,
        gender=resolved_gender,
        rank=rank,
        metadata_json=json.dumps(metadata or {}),
        exposure_id=exposure_id,
        client_log_id=client_log_id,
        client_event_at=client_event_at,
        client_sequence_number=client_sequence_number,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def serialize_log_row(row: models.Impression | models.Event) -> dict[str, Any]:
    timestamp = getattr(row, "timestamp", None) or datetime.now(timezone.utc)
    metadata = None
    if hasattr(row, "metadata_json") and row.metadata_json:
        try:
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            metadata = None
    return {
        "id": row.id,
        "user_id": getattr(row, "user_id", None),
        "session_id": row.session_id,
        "condition": row.condition,
        "video_id": row.video_id,
        "video_title": row.video_title,
        "surface": row.surface,
        "click_from": getattr(row, "click_from", None),
        "content_pool": row.content_pool,
        "gender": getattr(row, "gender", None) or "unspecified",
        "rank": row.rank,
        "exposure_id": getattr(row, "exposure_id", None),
        "client_log_id": getattr(row, "client_log_id", None),
        "client_event_at": iso_utc(getattr(row, "client_event_at", None)),
        "client_sequence_number": getattr(row, "client_sequence_number", None),
        "timestamp": iso_utc(timestamp),
        "metadata": metadata,
    }
