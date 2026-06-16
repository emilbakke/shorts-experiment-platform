import type { Condition, EntrySurveyPayload, EventPayload, ExperimentSession, LogPayload, StudyPostSurveyPayload, StudyPreSurveyPayload } from "./types";
import { backendAction } from "./backend-bridge";

type StoredLog = LogPayload & { id: string; timestamp: string };
type StoredEvent = EventPayload & { id: string; timestamp: string };
type StoredSearch = { id: string; query: string; result_count: number; user_id?: string; session_id?: string; condition: Condition; timestamp: string };
type StoredSession = ExperimentSession;
type LogsPayload = {
  impressions: StoredLog[];
  events: StoredEvent[];
  searches: StoredSearch[];
  sessions: StoredSession[];
};

function fallbackId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function withUserId<T extends { user_id?: string | null; session_id?: string | null }>(payload: T): T & { user_id: string } {
  return { ...payload, user_id: payload.user_id || payload.session_id || fallbackId("user") };
}

export function createSession(condition: Condition = "control_recommendation", user_id: string = fallbackId("user")) {
  return backendAction<StoredSession>("session", { condition, user_id });
}

export function ensureSession(session_id: string, condition: Condition = "control_recommendation", user_id?: string, reel_duration_seconds?: number) {
  return backendAction<StoredSession>("ensure_session", { session_id, condition, user_id, reel_duration_seconds });
}

export function latestStudySession(user_id: string) {
  return backendAction<StoredSession | null>("latest_study_session", { user_id });
}

export function recordStudyParticipationStatus(payload: { session_id: string; condition: Condition; user_id: string; consent_status: "accepted" | "declined"; screened_reason?: string; norstat_pid?: string | null }) {
  return backendAction<StoredSession>("study_participation_status", payload);
}

export function prepareStudySession(session_id: string, condition: Condition, user_id: string, reel_duration_seconds: number) {
  return backendAction<StoredSession>("study_prepare", { session_id, condition, user_id, reel_duration_seconds });
}

export function activateStudyReel(session_id: string) {
  return backendAction<StoredSession>("study_reel_activate", { session_id });
}

export function completeStudyReel(session_id: string) {
  return backendAction<StoredSession>("study_reel_complete", { session_id });
}

export function completeStudyPost(session_id: string) {
  return backendAction<StoredSession>("study_complete", { session_id });
}

export function submitStudyPreSurvey(payload: StudyPreSurveyPayload) {
  return backendAction<StoredSession>("study_pre_survey", payload);
}

export function submitStudyPostSurvey(payload: StudyPostSurveyPayload) {
  return backendAction<StoredSession>("study_post_survey", payload);
}

export function submitEntrySurvey(payload: EntrySurveyPayload) {
  return backendAction<StoredSession>("survey", payload);
}

export function addImpression(payload: LogPayload): Promise<StoredLog> {
  return backendAction<StoredLog>("impression", withUserId(payload));
}

export function addEvent(payload: EventPayload): Promise<StoredEvent> {
  return backendAction<StoredEvent>("event", withUserId(payload));
}

export function addSearch(query: string, resultCount: number, condition: Condition = "control_recommendation", session_id?: string, user_id?: string) {
  void resultCount;
  return backendAction<{ query: string; condition: Condition; results: unknown[] }>("search", {
    q: query,
    condition,
    session_id,
    user_id: user_id || session_id,
  });
}

export function getLogs(): Promise<LogsPayload> {
  return backendAction<LogsPayload>("logs");
}

export function resetLogs(): Promise<LogsPayload> {
  return backendAction<LogsPayload>("reset_logs");
}
