import uuid
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime
from .database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    username = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    condition = Column(String, nullable=False, default="control_recommendation")
    survey_completed = Column(Boolean, nullable=False, default=False)
    gender = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    age_group = Column(String, nullable=True)
    household_living_arrangement = Column(String, nullable=True)
    education = Column(String, nullable=True)
    education_level = Column(String, nullable=True)
    region_dk = Column(String, nullable=True)
    left_right_orientation = Column(Integer, nullable=True)
    political_orientation = Column(Integer, nullable=True)
    video_platform_use = Column(String, nullable=True)
    typical_video_platforms = Column(Text, nullable=True)
    cohabitation_status = Column(String, nullable=True)
    employment_status = Column(String, nullable=True)
    norstat_pid = Column(String, nullable=True)
    feminist_attitude = Column(Integer, nullable=True)
    feminism_taken_too_far = Column(Integer, nullable=True)
    traditional_gender_attitude = Column(Integer, nullable=True)
    harder_to_be_a_man_today = Column(Integer, nullable=True)
    social_division = Column(Integer, nullable=True)
    gender_conflict_exaggeration = Column(Integer, nullable=True)
    online_misinformation = Column(Integer, nullable=True)
    perceived_content_type = Column(String, nullable=True)
    study_state = Column(String, nullable=False, default="entry")
    reel_duration_seconds = Column(Integer, nullable=False, default=240)
    reel_started_at = Column(DateTime(timezone=True), nullable=True)
    reel_expires_at = Column(DateTime(timezone=True), nullable=True)
    reel_completed_at = Column(DateTime(timezone=True), nullable=True)
    post_survey_completed_at = Column(DateTime(timezone=True), nullable=True)
    consent_status = Column(String, nullable=True)
    consented_at = Column(DateTime(timezone=True), nullable=True)
    screened_reason = Column(String, nullable=True)
    screened_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ContentPool(Base):
    __tablename__ = "content_pools"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, default=gen_uuid)
    content_pool_id = Column(String, ForeignKey("content_pools.id"), nullable=True)
    content_pool = Column(String, nullable=False, default="safe", index=True)
    title = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    topic = Column(String, nullable=False, index=True)
    thumbnail_url = Column(String, nullable=False)
    video_url = Column(String, nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=0)
    views = Column(Integer, nullable=False, default=0)
    popularity_score = Column(Float, nullable=False, default=0)
    freshness_score = Column(Float, nullable=False, default=0)
    is_short = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    youtube_id = Column(String, unique=True, index=True)
    source = Column(String, default="youtube")
    creator_slug = Column(String, nullable=True, index=True)
    review_group = Column(String, nullable=True, index=True)
    channel_id = Column(String, nullable=True, index=True)
    ingest_source_type = Column(String, nullable=True)
    ingest_query = Column(String, nullable=True)
    short_confidence = Column(String, nullable=True)
    embeddable = Column(Boolean, nullable=False, default=True)
    embeddable_checked_at = Column(DateTime(timezone=True), nullable=True)

class Impression(Base):
    __tablename__ = "impressions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    condition = Column(String, nullable=False, default="control_recommendation")
    video_id = Column(String, nullable=False)
    video_title = Column(String, nullable=False)
    surface = Column(String, nullable=False)
    click_from = Column(String, nullable=False)
    content_pool = Column(String, nullable=False, default="safe")
    gender = Column(String, nullable=False, default="unspecified")
    rank = Column(Integer, nullable=False)
    exposure_id = Column(String, nullable=True, index=True)
    client_log_id = Column(String, nullable=True, unique=True, index=True)
    client_event_at = Column(DateTime(timezone=True), nullable=True)
    client_sequence_number = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    condition = Column(String, nullable=False, default="control_recommendation")
    video_id = Column(String, nullable=False)
    video_title = Column(String, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    surface = Column(String, nullable=False)
    click_from = Column(String, nullable=False)
    content_pool = Column(String, nullable=False, default="safe")
    gender = Column(String, nullable=False, default="unspecified")
    rank = Column(Integer, nullable=False)
    metadata_json = Column(Text, nullable=True)
    exposure_id = Column(String, nullable=True, index=True)
    client_log_id = Column(String, nullable=True, unique=True, index=True)
    client_event_at = Column(DateTime(timezone=True), nullable=True)
    client_sequence_number = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    condition = Column(String, nullable=False, default="control_recommendation")
    gender = Column(String, nullable=True)
    query = Column(String, nullable=False)
    result_count = Column(Integer, nullable=False, default=0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


CONTENT_MODELS = (ContentPool, Video)
BEHAVIOR_MODELS = (User, Session, Impression, Event, SearchQuery)
