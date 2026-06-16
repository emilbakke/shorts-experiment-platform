"use client";

import { defaultCondition, isCondition } from "./experiment";
import type { Condition, EventPayload, LoggingContext, LogPayload, Surface, Video } from "./types";

const surveyStorageKey = "exp-video-entry-survey";

export function sessionId(): string {
  const key = "exp-video-session";
  let value = window.localStorage.getItem(key);
  if (!value) {
    value = `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, value);
  }
  return value;
}

export function userId(): string {
  const key = "exp-video-user";
  let value = window.localStorage.getItem(key);
  if (!value) {
    value = `user-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(key, value);
  }
  return value;
}

export function surveyCompletionKey(): string {
  return `${surveyStorageKey}:${sessionId()}`;
}

export function storedSurveyAnswers(): Record<string, unknown> | null {
  const raw = window.localStorage.getItem(surveyCompletionKey());
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function surveyCompleted(): boolean {
  return storedSurveyAnswers() !== null;
}

export function persistSurveyAnswers(answers: Record<string, unknown>) {
  window.localStorage.setItem(surveyCompletionKey(), JSON.stringify(answers));
}

export function currentGender(): string {
  const answers = storedSurveyAnswers();
  const gender = typeof answers?.gender === "string" ? answers.gender.trim() : "";
  return gender || "unspecified";
}

export function activeCondition(): Condition {
  const key = "exp-video-condition";
  const fromUrl = new URLSearchParams(window.location.search).get("condition");
  if (isCondition(fromUrl)) {
    window.localStorage.setItem(key, fromUrl);
    return fromUrl;
  }
  window.localStorage.setItem(key, defaultCondition);
  return defaultCondition;
}

const outboxKey = "exp-video-log-outbox-v1";
type OutboxItem = { id: string; path: string; body: Record<string, unknown> };
let flushPromise: Promise<void> | null = null;
let retryTimer: number | null = null;

function readOutbox(): OutboxItem[] {
  try {
    return JSON.parse(window.localStorage.getItem(outboxKey) ?? "[]") as OutboxItem[];
  } catch {
    return [];
  }
}

function writeOutbox(items: OutboxItem[]) {
  window.localStorage.setItem(outboxKey, JSON.stringify(items));
}

function newClientLogId(): string {
  return `client-log-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function nextClientSequenceNumber(resolvedSessionId: string): number {
  const key = `exp-video-client-sequence:${resolvedSessionId}`;
  const next = Number(window.localStorage.getItem(key) ?? "0") + 1;
  window.localStorage.setItem(key, String(next));
  return next;
}

export async function sendJsonNow(path: string, body: unknown) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    keepalive: true,
  });
  if (!response.ok) throw new Error(`Logging request failed: ${response.status}`);
}

function scheduleRetry() {
  if (retryTimer !== null) return;
  retryTimer = window.setTimeout(() => {
    retryTimer = null;
    void flushLogOutbox();
  }, 1500);
}

export function flushLogOutbox(): Promise<void> {
  if (flushPromise) return flushPromise;
  flushPromise = (async () => {
    while (true) {
      const items = readOutbox();
      const item = items[0];
      if (!item) return;
      try {
        await sendJsonNow(item.path, item.body);
      } catch {
        scheduleRetry();
        return;
      }
      const latest = readOutbox();
      writeOutbox(latest.filter((candidate) => candidate.id !== item.id));
    }
  })().finally(() => { flushPromise = null; });
  return flushPromise;
}

async function postJson(path: string, body: Record<string, unknown>) {
  const id = typeof body.client_log_id === "string" ? body.client_log_id : newClientLogId();
  const item = { id, path, body: { ...body, client_log_id: id } };
  const pending = readOutbox();
  if (path === "/api/events" && body.event_type === "click") {
    const matchingImpressionIndex = pending.findIndex((candidate) =>
      candidate.path === "/api/impressions"
      && candidate.body.session_id === body.session_id
      && candidate.body.video_id === body.video_id
      && candidate.body.surface === body.surface,
    );
    if (matchingImpressionIndex >= 0) {
      const matchingImpression = pending[matchingImpressionIndex];
      writeOutbox([matchingImpression, item, ...pending.filter((_, index) => index !== matchingImpressionIndex)]);
    } else {
      writeOutbox([item, ...pending]);
    }
  } else if (path === "/api/impressions" && body.rank === 1) {
    writeOutbox([item, ...pending]);
  } else {
    writeOutbox([...pending, item]);
  }
  void flushLogOutbox().then(() => {
    if (readOutbox().length > 0) void flushLogOutbox();
  });
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => void flushLogOutbox());
  window.addEventListener("pagehide", () => void flushLogOutbox());
  window.setTimeout(() => void flushLogOutbox(), 0);
}

export function payloadFor(video: Video, surface: Surface, clickFrom: Surface, condition: Condition = activeCondition(), context: LoggingContext = {}): LogPayload {
  const resolvedSessionId = context.sessionId ?? sessionId();
  return {
    user_id: context.userId ?? userId(),
    video_id: video.id,
    video_title: video.title,
    surface,
    click_from: clickFrom,
    condition,
    content_pool: video.contentPool,
    gender: currentGender(),
    rank: video.rank ?? 0,
    session_id: resolvedSessionId,
    exposure_id: context.exposureId,
    client_event_at: new Date().toISOString(),
    client_sequence_number: nextClientSequenceNumber(resolvedSessionId),
  };
}

export async function logImpression(video: Video, surface: Surface, clickFrom: Surface = surface, condition: Condition = activeCondition(), context: LoggingContext = {}) {
  await postJson("/api/impressions", payloadFor(video, surface, clickFrom, condition, context));
}

export async function logEvent(payload: EventPayload) {
  await postJson("/api/events", payload);
}
