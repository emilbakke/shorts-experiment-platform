"use client";

import type { Condition, ExperimentSession } from "./types";
import { legacyStudyBasePath, studyBasePath } from "./study-routes";
export { legacyStudyBasePath, studyBasePath } from "./study-routes";

export type StudyState =
  | "entry"
  | "pre_survey"
  | "instructions"
  | "assigned"
  | "reel_active"
  | "reel_completed"
  | "post_survey"
  | "complete"
  | "debrief"
  | "interrupted";

export type StudyAssignment = "control" | "treatment";

export type StudySession = {
  study_id: string;
  state: StudyState;
  assignment: StudyAssignment | null;
  session_id: string | null;
  norstat_pid: string | null;
  started_at: string | null;
  completed_at: string | null;
};

const storageKey = "exp-video-study-shorts-experiment";

function newStudySession(): StudySession {
  return {
    study_id: `study-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    state: "entry",
    assignment: null,
    session_id: null,
    norstat_pid: null,
    started_at: null,
    completed_at: null,
  };
}

export function readExistingStudySession(): StudySession | null {
  const raw = window.localStorage.getItem(storageKey);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StudySession;
  } catch {
    return null;
  }
}

export function readStudySession(): StudySession {
  const raw = window.localStorage.getItem(storageKey);
  if (!raw) {
    const created = newStudySession();
    writeStudySession(created);
    return created;
  }

  try {
    return JSON.parse(raw) as StudySession;
  } catch {
    const created = newStudySession();
    writeStudySession(created);
    return created;
  }
}

export function writeStudySession(session: StudySession) {
  window.localStorage.setItem(storageKey, JSON.stringify(session));
}

export function patchStudySession(patch: Partial<StudySession>): StudySession {
  const next = { ...readStudySession(), ...patch };
  writeStudySession(next);
  return next;
}

export function resetStudySession(): StudySession {
  const created = newStudySession();
  writeStudySession(created);
  return created;
}

export function clearStudySurveyArtifacts() {
  window.localStorage.removeItem("exp-video-study-consent");
  window.localStorage.removeItem("exp-video-study-pre");
  window.localStorage.removeItem("exp-video-study-post");
}

export function resetStudyForPreSurvey(): StudySession {
  clearStudySurveyArtifacts();
  const created = resetStudySession();
  const next = { ...created, state: "pre_survey" as const };
  writeStudySession(next);
  return next;
}

export function assignStudyCondition(): StudyAssignment {
  return Math.random() < 0.5 ? "control" : "treatment";
}

export function conditionForAssignment(assignment: StudyAssignment): Condition {
  return assignment === "treatment" ? "treatment_problematic_content" : "control_recommendation";
}

export function routeForStudyState(state: StudyState): string {
  if (state === "pre_survey") return `${studyBasePath}/pre`;
  if (state === "instructions") return `${studyBasePath}/instructions`;
  if (state === "assigned" || state === "reel_active" || state === "interrupted") return `${studyBasePath}/reel`;
  if (state === "reel_completed" || state === "post_survey") return `${studyBasePath}/post`;
  if (state === "complete") return `${studyBasePath}/complete`;
  if (state === "debrief") return `${studyBasePath}/debrief`;
  return studyBasePath;
}

export const postSurveyDebriefGraceMs = 2 * 60 * 1000;

function timestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function incompleteReturnRoute(session: StudySession, serverSession?: ExperimentSession | null, nowMs = Date.now()): string {
  const serverState = serverSession?.study_state;
  if (serverState === "complete") return `${studyBasePath}/complete`;
  if (!serverSession && session.state === "complete") return `${studyBasePath}/complete`;
  if (!session.session_id) return routeForStudyState(session.state);

  const expiresAtMs = timestampMs(serverSession?.reel_expires_at);
  const completedAtMs = timestampMs(serverSession?.reel_completed_at);
  const exposureEndMs = expiresAtMs ?? completedAtMs;

  if (exposureEndMs !== null) {
    if (nowMs < exposureEndMs) return `${studyBasePath}/reel`;
    if (nowMs - exposureEndMs <= postSurveyDebriefGraceMs) return `${studyBasePath}/post`;
    return `${studyBasePath}/debrief`;
  }

  if (serverState === "reel_completed" || serverState === "post_survey" || session.state === "reel_completed" || session.state === "post_survey") {
    return `${studyBasePath}/post`;
  }

  return routeForStudyState(session.state);
}

export function shouldActivateReelForReturn(session: StudySession, serverSession?: ExperimentSession | null): boolean {
  if (!session.session_id) return false;
  if (serverSession?.study_state === "complete") return false;
  if (!serverSession && session.state === "complete") return false;
  if (serverSession?.reel_started_at || serverSession?.reel_expires_at) return true;
  return ["reel_active", "interrupted", "reel_completed", "post_survey", "debrief"].includes(session.state);
}

export function stepForStudyState(state: StudyState): number {
  if (state === "entry" || state === "pre_survey") return 1;
  if (state === "instructions" || state === "assigned" || state === "reel_active" || state === "interrupted") return 2;
  if (state === "reel_completed" || state === "post_survey") return 3;
  return 4;
}

export function isStudyPath(pathname: string): boolean {
  return pathname.startsWith(studyBasePath) || pathname.startsWith(legacyStudyBasePath);
}
