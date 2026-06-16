from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

Surface = Literal["search", "recommendation", "related", "shorts"]
EventType = Literal[
    "click",
    "watch_start",
    "progress",
    "complete",
    "visibility_hidden",
    "visibility_visible",
    "window_blur",
    "window_focus",
    "playback_waiting",
    "playback_stalled",
    "playback_pause",
    "playback_error",
    "exposure_end",
]
Condition = Literal["control_recommendation", "treatment_search", "treatment_problematic_content"]
ContentPool = Literal["safe", "problematic"]


class ImpressionIn(BaseModel):
    user_id: str | None = None
    video_id: str
    video_title: str
    surface: Surface
    click_from: Surface
    condition: Condition
    content_pool: ContentPool
    gender: str | None = None
    rank: int = Field(ge=0)
    session_id: str
    exposure_id: str | None = None
    client_log_id: str | None = None
    client_event_at: datetime | None = None
    client_sequence_number: int | None = Field(default=None, ge=1)


class EventIn(BaseModel):
    user_id: str | None = None
    video_id: str
    video_title: str
    surface: Surface
    click_from: Surface
    condition: Condition
    content_pool: ContentPool
    gender: str | None = None
    rank: int = Field(ge=0)
    event_type: EventType
    session_id: str
    metadata: dict[str, Any] | None = None
    exposure_id: str | None = None
    client_log_id: str | None = None
    client_event_at: datetime | None = None
    client_sequence_number: int | None = Field(default=None, ge=1)


class SessionIn(BaseModel):
    condition: Condition | None = None
    user_id: str | None = None
    reel_duration_seconds: int | None = Field(default=None, ge=1, le=4800)


class EntrySurveyIn(BaseModel):
    user_id: str | None = None
    condition: Condition | None = None
    gender: str = Field(min_length=1)
    age: int = Field(ge=13, le=120)
    household_living_arrangement: Literal[
        "living_with_parents",
        "living_alone",
        "living_with_partner_or_roommate",
    ]
    education: str = Field(min_length=1)
    region_dk: Literal[
        "hovedstaden",
        "sjælland",
        "syddanmark",
        "midtjylland",
        "nordjylland",
    ]
    left_right_orientation: int = Field(ge=0, le=10)


class StudyPreSurveyIn(BaseModel):
    session_id: str
    user_id: str | None = None
    condition: Condition | None = None
    age_group: str = Field(min_length=1)
    gender: str = Field(min_length=1)
    video_platform_use: str = Field(min_length=1)
    political_orientation: int = Field(ge=0, le=10)
    education_level: str = Field(min_length=1)
    typical_video_platforms: list[str] = []
    cohabitation_status: str = Field(min_length=1)
    employment_status: str = Field(min_length=1)
    norstat_pid: str | None = None


class StudyPostSurveyIn(BaseModel):
    session_id: str
    feminist_attitude: int = Field(ge=1, le=7)
    feminism_taken_too_far: int = Field(ge=1, le=7)
    traditional_gender_attitude: int = Field(ge=1, le=7)
    harder_to_be_a_man_today: int = Field(ge=1, le=7)
    social_division: int = Field(ge=1, le=7)
    gender_conflict_exaggeration: int = Field(ge=1, le=7)
    online_misinformation: int = Field(ge=1, le=7)
    perceived_content_type: str = Field(min_length=1)


class LegacyEventIn(BaseModel):
    user_id: str | None = None
    video_id: str
    video_title: str
    event_type: EventType
    click_from: Surface
    condition: Condition
    content_pool: ContentPool
    gender: str | None = None
    surface: Surface | None = None
    rank: int = Field(default=0, ge=0)
    session_id: str | None = None
    metadata: dict[str, Any] | None = None
