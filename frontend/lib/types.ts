export type Surface = "search" | "recommendation" | "related" | "shorts";
export type EventType =
  | "click"
  | "watch_start"
  | "progress"
  | "complete"
  | "visibility_hidden"
  | "visibility_visible"
  | "window_blur"
  | "window_focus"
  | "playback_waiting"
  | "playback_stalled"
  | "playback_pause"
  | "playback_error"
  | "exposure_end";
export type Condition = "control_recommendation" | "treatment_search" | "treatment_problematic_content";
export type ContentPool = "safe" | "problematic";
export type PoolMode = ContentPool | "mixed";

export type Video = {
  id: string;
  routeId?: string;
  title: string;
  contentPool: ContentPool;
  channel: string;
  topic: string;
  thumbnailUrl: string;
  videoUrl: string;
  durationSeconds: number;
  views: number;
  popularityScore: number;
  freshnessScore: number;
  isShort: boolean;
  rank?: number;
  youtubeId?: string;
  source?: string;
};

export type LogPayload = {
  user_id: string;
  video_id: string;
  video_title: string;
  surface: Surface;
  click_from: Surface;
  condition: Condition;
  content_pool: ContentPool;
  gender: string;
  rank: number;
  session_id: string;
  exposure_id?: string;
  client_log_id?: string;
  client_event_at?: string;
  client_sequence_number?: number;
};

export type LoggingContext = {
  userId?: string;
  sessionId?: string;
  exposureId?: string;
};

export type EventPayload = LogPayload & {
  event_type: EventType;
  metadata?: Record<string, unknown>;
};

export type EntrySurveyPayload = {
  session_id: string;
  user_id: string;
  condition: Condition;
  gender: string;
  age: number;
  household_living_arrangement: "living_with_parents" | "living_alone" | "living_with_partner_or_roommate";
  education: string;
  region_dk: "hovedstaden" | "sjælland" | "syddanmark" | "midtjylland" | "nordjylland";
  left_right_orientation: number;
};

export type StudyPreSurveyPayload = {
  session_id: string;
  user_id: string;
  condition: Condition;
  age_group: string;
  gender: string;
  video_platform_use: string;
  political_orientation: number;
  education_level: string;
  typical_video_platforms: string[];
  cohabitation_status: string;
  employment_status: string;
  norstat_pid?: string | null;
};

export type StudyPostSurveyPayload = {
  session_id: string;
  feminist_attitude: number;
  feminism_taken_too_far: number;
  traditional_gender_attitude: number;
  harder_to_be_a_man_today: number;
  social_division: number;
  gender_conflict_exaggeration: number;
  online_misinformation: number;
  perceived_content_type: string;
};

export type ExperimentSession = {
  id: string;
  session_id: string;
  user_id?: string | null;
  condition: Condition;
  survey_completed: boolean;
  gender?: string | null;
  age?: number | null;
  household_living_arrangement?: string | null;
  education?: string | null;
  region_dk?: string | null;
  left_right_orientation?: number | null;
  age_group?: string | null;
  education_level?: string | null;
  political_orientation?: number | null;
  video_platform_use?: string | null;
  typical_video_platforms?: string | null;
  cohabitation_status?: string | null;
  employment_status?: string | null;
  norstat_pid?: string | null;
  feminist_attitude?: number | null;
  feminism_taken_too_far?: number | null;
  traditional_gender_attitude?: number | null;
  harder_to_be_a_man_today?: number | null;
  social_division?: number | null;
  gender_conflict_exaggeration?: number | null;
  online_misinformation?: number | null;
  perceived_content_type?: string | null;
  study_state?: string | null;
  reel_duration_seconds?: number | null;
  reel_started_at?: string | null;
  reel_expires_at?: string | null;
  reel_completed_at?: string | null;
  post_survey_completed_at?: string | null;
  created_at: string;
};
