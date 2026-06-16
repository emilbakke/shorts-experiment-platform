"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentTimer } from "./ExperimentTimer";
import { ShortsReel } from "@/components/ShortsReel";
import { conditionForAssignment, patchStudySession, readStudySession, resetStudySession, routeForStudyState, studyBasePath } from "@/lib/study-session";
import { userId } from "@/lib/analytics";
import { norstatUserId } from "@/lib/norstat";
import type { ExperimentSession, Video } from "@/lib/types";

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

async function jsonOrThrow<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload && typeof payload === "object" && "error" in payload ? String(payload.error) : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export function StudyReelScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [remainingSeconds, setRemainingSeconds] = useState(240);
  const [totalSeconds, setTotalSeconds] = useState(240);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const completionRequested = useRef(false);
  const activationRequested = useRef(false);

  const durationSeconds = useMemo(() => {
    const requested = Number(searchParams.get("duration_seconds") ?? "240");
    return Number.isFinite(requested) && requested > 0 ? Math.floor(requested) : 240;
  }, [searchParams]);

  useEffect(() => {
    const session = readStudySession();
    completionRequested.current = false;
    activationRequested.current = false;
    if (!session.assignment || !["assigned", "reel_active"].includes(session.state)) {
      router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
      return;
    }

    patchStudySession({ state: "reel_active" });

    const condition = conditionForAssignment(session.assignment);
    const localSessionId = session.session_id;
    if (!localSessionId) {
      router.replace(`${studyBasePath}${suffix(searchParams)}`);
      return;
    }

    Promise.all([
      fetch(`/api/session?${new URLSearchParams({ session_id: localSessionId, reel_duration_seconds: String(durationSeconds) }).toString()}`).then((response) => jsonOrThrow<ExperimentSession>(response)),
      fetch(`/api/study/shorts?${new URLSearchParams({ condition, session_id: localSessionId }).toString()}`).then((response) => jsonOrThrow<Video[]>(response)),
    ])
      .then(([sessionPayload, videoPayload]) => {
        if (sessionPayload.study_state === "reel_completed" || sessionPayload.study_state === "post_survey" || sessionPayload.study_state === "complete") {
          patchStudySession({ state: sessionPayload.study_state === "complete" ? "complete" : "reel_completed" });
          router.replace(`${sessionPayload.study_state === "complete" ? `${studyBasePath}/complete` : `${studyBasePath}/post`}${suffix(searchParams)}`);
          return;
        }
        if (sessionPayload.reel_expires_at) {
          const parsed = Date.parse(sessionPayload.reel_expires_at);
          if (Number.isFinite(parsed)) {
            setExpiresAt(parsed);
            setRemainingSeconds(Math.max(0, Math.ceil((parsed - Date.now()) / 1000)));
          }
        }
        const pendingDuration = sessionPayload.reel_expires_at ? (sessionPayload.reel_duration_seconds ?? durationSeconds) : durationSeconds;
        setTotalSeconds(pendingDuration);
        setRemainingSeconds(pendingDuration);
        setVideos(videoPayload);
      })
      .catch(() => {
        resetStudySession();
        router.replace(`${studyBasePath}${suffix(searchParams)}`);
      })
      .finally(() => setLoading(false));
  }, [durationSeconds, router, searchParams]);

  const startExposureTimer = useCallback(() => {
    if (activationRequested.current || expiresAt !== null) return;
    const session = readStudySession();
    if (!session.session_id) return;
    activationRequested.current = true;
    void fetch("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "study_reel_activate", session_id: session.session_id }),
    })
      .then((response) => jsonOrThrow<ExperimentSession>(response))
      .then((sessionPayload) => {
        const parsed = sessionPayload.reel_expires_at ? Date.parse(sessionPayload.reel_expires_at) : Number.NaN;
        if (!Number.isFinite(parsed)) throw new Error("reel activation did not return an expiry");
        setTotalSeconds(sessionPayload.reel_duration_seconds ?? durationSeconds);
        setExpiresAt(parsed);
        setRemainingSeconds(Math.max(0, Math.ceil((parsed - Date.now()) / 1000)));
      })
      .catch(() => {
        activationRequested.current = false;
      });
  }, [durationSeconds, expiresAt]);

  useEffect(() => {
    if (loading || expiresAt === null) return undefined;
    const timer = window.setInterval(() => {
      const nextRemaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
      setRemainingSeconds(nextRemaining);
      if (nextRemaining <= 0 && !completionRequested.current) {
        completionRequested.current = true;
        const session = readStudySession();
        patchStudySession({ state: "reel_completed" });
        if (session.session_id) {
          void fetch("/api/session", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ action: "study_reel_complete", session_id: session.session_id }),
          });
        }
        router.replace(`${studyBasePath}/post${suffix(searchParams)}`);
      }
    }, 1000);

    return () => window.clearInterval(timer);
  }, [expiresAt, loading, router, searchParams, videos]);

  if (loading) {
    return (
      <section className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
        <div className="rounded-3xl border border-white/10 bg-white/6 px-6 py-5 text-sm text-white/72 shadow-2xl">Indlæser videosessionen…</div>
      </section>
    );
  }

  if (videos.length === 0) {
    return (
      <section className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
        <div className="rounded-3xl border border-white/10 bg-white/6 px-6 py-5 text-sm text-white/72 shadow-2xl">Der er endnu ingen korte videoer tilgængelige for denne session.</div>
      </section>
    );
  }

  const currentStudySession = readStudySession();
  const loggingUserId = currentStudySession.norstat_pid ? norstatUserId(currentStudySession.norstat_pid, "") : userId();
  const loggingSessionId = currentStudySession.session_id ?? undefined;

  return (
    <section className="relative min-h-screen bg-zinc-950">
      <div className="pointer-events-none absolute left-4 top-[calc(env(safe-area-inset-top)+3.25rem)] z-[60] sm:left-6 sm:top-6">
        <ExperimentTimer remainingSeconds={remainingSeconds} totalSeconds={totalSeconds} />
      </div>
      <ShortsReel
        videos={videos}
        initialIndex={0}
        condition={conditionForAssignment(currentStudySession.assignment ?? "control")}
        loggingUserId={loggingUserId}
        loggingSessionId={loggingSessionId}
        onFirstVideoStart={startExposureTimer}
        exposureEndsAt={expiresAt}
        topOffsetClass="top-0"
        closeLabel="Forlad sessionen"
        hideViewCount
        onClose={() => {
          patchStudySession({ state: "interrupted" });
          router.replace(`${studyBasePath}${suffix(searchParams)}`);
        }}
      />
    </section>
  );
}
