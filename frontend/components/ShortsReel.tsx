"use client";

import type { TouchEvent as ReactTouchEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { logEvent, logImpression, payloadFor } from "@/lib/analytics";
import type { Condition, Video } from "@/lib/types";
import { formatViews, youtubeEmbedUrl } from "@/lib/video-utils";

function ShortsActionButton({
  label,
  onClick,
  active = false,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative z-20 flex w-16 flex-col items-center gap-1.5 text-white"
      aria-label={label}
      data-active={active ? "true" : "false"}
    >
      <span className={`flex h-12 w-12 items-center justify-center rounded-full shadow-lg backdrop-blur transition ${active ? "bg-red-600 text-white shadow-red-900/40" : "bg-black/35 shadow-black/35 group-hover:bg-black/45"}`}>
        {children}
      </span>
      <span className="w-full text-center text-[11px] font-semibold leading-none text-white/88">{label}</span>
    </button>
  );
}

export function ShortsReel({
  videos,
  initialIndex,
  condition,
  topOffsetClass = "top-14",
  hideViewCount = false,
  loggingUserId,
  loggingSessionId,
  onFirstVideoStart,
  exposureEndsAt,
}: {
  videos: Video[];
  initialIndex: number;
  condition: Condition;
  onClose: () => void;
  topOffsetClass?: string;
  closeLabel?: string;
  allowClose?: boolean;
  hideViewCount?: boolean;
  loggingUserId?: string;
  loggingSessionId?: string;
  onFirstVideoStart?: () => void;
  exposureEndsAt?: number | null;
}) {
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const [origin] = useState<string | undefined>(() => (typeof window === "undefined" ? undefined : window.location.origin));
  const [likedVideoIds, setLikedVideoIds] = useState<Record<string, boolean>>({});
  const [sharedVideoIds, setSharedVideoIds] = useState<Record<string, boolean>>({});
  const [firstVideoStartPending, setFirstVideoStartPending] = useState(true);
  const firstVideoStartPendingRef = useRef(true);
  const startLogged = useRef(false);
  const progressLogged = useRef(false);
  const completeLogged = useRef(false);
  const activeShownAtRef = useRef(Date.now());
  const playbackStartedAtRef = useRef<number | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const nativeVideoRef = useRef<HTMLVideoElement | null>(null);
  const hiddenAtRef = useRef<number | null>(null);
  const blurAtRef = useRef<number | null>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const exposureIdRef = useRef(`exposure-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const playingSegmentStartedAtRef = useRef<number | null>(null);
  const accumulatedPlayingMsRef = useRef(0);
  const finalizedExposureIdsRef = useRef(new Set<string>());
  const suppressNextPauseRef = useRef(false);
  const activeVideo = videos[Math.min(activeIndex, Math.max(videos.length - 1, 0))];
  const nextVideo = videos.length > 1 ? videos[(activeIndex + 1) % videos.length] : null;
  const previousVideo = videos.length > 1 ? videos[(activeIndex - 1 + videos.length) % videos.length] : null;
  const loggingContext = useMemo(() => ({ userId: loggingUserId, sessionId: loggingSessionId }), [loggingSessionId, loggingUserId]);
  const youtubeSrc = useMemo(() => (activeVideo ? youtubeEmbedUrl(activeVideo.videoUrl, true, origin, true, true) : null), [activeVideo, origin]);
  const isLiked = activeVideo ? likedVideoIds[activeVideo.id] === true : false;
  const isShared = activeVideo ? sharedVideoIds[activeVideo.id] === true : false;

  const postToYoutubePlayer = useCallback((func: "unMute" | "playVideo") => {
    if (!iframeRef.current?.contentWindow) return;
    iframeRef.current.contentWindow.postMessage(
      JSON.stringify({
        event: "command",
        func,
        args: [],
      }),
      "https://www.youtube-nocookie.com",
    );
  }, []);

  const ensurePlayback = useCallback(() => {
    if (firstVideoStartPendingRef.current) return;
    const activeNativeVideo = nativeVideoRef.current;
    if (activeNativeVideo) {
      activeNativeVideo.muted = false;
      activeNativeVideo.volume = 1;
      activeNativeVideo.playsInline = true;
      void activeNativeVideo.play().catch(() => {
        // iOS may require one more user interaction; the transparent shield and swipe handlers retry playback.
      });
    }
    postToYoutubePlayer("playVideo");
    window.setTimeout(() => postToYoutubePlayer("unMute"), 350);
    window.setTimeout(() => postToYoutubePlayer("unMute"), 900);
    window.setTimeout(() => postToYoutubePlayer("unMute"), 1600);
  }, [activeVideo, postToYoutubePlayer]);

  const startFirstVideo = useCallback(() => {
    firstVideoStartPendingRef.current = false;
    setFirstVideoStartPending(false);
    onFirstVideoStart?.();
    ensurePlayback();
  }, [ensurePlayback, onFirstVideoStart]);

  const switchNativePlayback = useCallback((targetVideo: Video | null | undefined) => {
    const nativeVideo = nativeVideoRef.current;
    if (!nativeVideo || !targetVideo || youtubeEmbedUrl(targetVideo.videoUrl, false)) return;

    suppressNextPauseRef.current = true;
    nativeVideo.pause();
    nativeVideo.src = targetVideo.videoUrl;
    nativeVideo.load();
    nativeVideo.muted = false;
    nativeVideo.volume = 1;
    nativeVideo.playsInline = true;
    void nativeVideo.play().catch(() => {
      // The persistent playback shield remains available if Safari rejects this gesture attempt.
    });
  }, []);

  const emit = useCallback(
    async (
      event_type:
        | "watch_start"
        | "progress"
        | "complete"
        | "click"
        | "visibility_hidden"
        | "visibility_visible"
        | "window_blur"
        | "window_focus"
        | "playback_waiting"
        | "playback_stalled"
        | "playback_pause"
        | "playback_error"
        | "exposure_end",
      metadata?: Record<string, unknown>,
    ) => {
      if (!activeVideo) return;
      const exposureContext = { ...loggingContext, exposureId: exposureIdRef.current };
      if (event_type === "click") {
        await logImpression(activeVideo, "shorts", "shorts", condition, exposureContext);
      }
      await logEvent({ ...payloadFor(activeVideo, "shorts", "shorts", condition, exposureContext), event_type, metadata });
    },
    [activeVideo, condition, loggingContext],
  );

  const emitStart = useCallback(
    async (metadata?: Record<string, unknown>) => {
      if (!activeVideo || startLogged.current) return;
      startLogged.current = true;
      await logImpression(activeVideo, "shorts", "shorts", condition, { ...loggingContext, exposureId: exposureIdRef.current });
      await emit("watch_start", metadata);
    },
    [activeVideo, condition, emit, loggingContext],
  );

  const emitProgress = useCallback(
    (metadata?: Record<string, unknown>) => {
      if (progressLogged.current) return;
      progressLogged.current = true;
      void emit("progress", metadata);
    },
    [emit],
  );

  const emitComplete = useCallback(
    (metadata?: Record<string, unknown>) => {
      if (completeLogged.current) return;
      completeLogged.current = true;
      void emit("complete", metadata);
    },
    [emit],
  );

  const actualPlayingMs = useCallback((stopSegment = false) => {
    const now = Date.now();
    const segmentStartedAt = playingSegmentStartedAtRef.current;
    const total = accumulatedPlayingMsRef.current + (segmentStartedAt === null ? 0 : Math.max(0, now - segmentStartedAt));
    if (stopSegment && segmentStartedAt !== null) {
      accumulatedPlayingMsRef.current = total;
      playingSegmentStartedAtRef.current = null;
    }
    return total;
  }, []);

  const playbackDwellMetadata = useCallback(() => {
    const playbackStartedAt = playbackStartedAtRef.current;
    const now = Date.now();
    return {
      surface_dwell_ms: Math.max(0, now - activeShownAtRef.current),
      playback_started: playbackStartedAt !== null,
      startup_delay_ms: playbackStartedAt === null ? null : Math.max(0, playbackStartedAt - activeShownAtRef.current),
      playback_dwell_ms: playbackStartedAt === null ? 0 : Math.max(0, now - playbackStartedAt),
      actual_playing_ms: actualPlayingMs(),
    };
  }, [actualPlayingMs]);

  const prepareForNextPlayback = useCallback(() => {
    firstVideoStartPendingRef.current = false;
    setFirstVideoStartPending(false);
    actualPlayingMs(true);
    exposureIdRef.current = `exposure-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    accumulatedPlayingMsRef.current = 0;
    playingSegmentStartedAtRef.current = null;
    playbackStartedAtRef.current = null;
    activeShownAtRef.current = Date.now();
  }, [actualPlayingMs]);

  const nextShort = useCallback(
    (action = "next") => {
      if (videos.length === 0) return;
      if (firstVideoStartPendingRef.current) startFirstVideo();
      const playbackMetadata = playbackDwellMetadata();
      void emit("click", { action, ...playbackMetadata });
      prepareForNextPlayback();
      switchNativePlayback(nextVideo);
      setActiveIndex((current) => (current + 1) % videos.length);
    },
    [emit, nextVideo, playbackDwellMetadata, prepareForNextPlayback, startFirstVideo, switchNativePlayback, videos.length],
  );

  const previousShort = useCallback(
    (action = "previous") => {
      if (videos.length === 0) return;
      if (firstVideoStartPendingRef.current) startFirstVideo();
      const playbackMetadata = playbackDwellMetadata();
      void emit("click", { action, ...playbackMetadata });
      prepareForNextPlayback();
      switchNativePlayback(previousVideo);
      setActiveIndex((current) => (current - 1 + videos.length) % videos.length);
    },
    [emit, playbackDwellMetadata, prepareForNextPlayback, previousVideo, startFirstVideo, switchNativePlayback, videos.length],
  );

  useEffect(() => {
    const video = nativeVideoRef.current;
    if (video) {
      video.muted = false;
      video.volume = 1;
      video.playsInline = true;
    }
    ensurePlayback();
  }, [activeVideo?.id, activeVideo?.videoUrl, ensurePlayback]);

  useEffect(() => {
    if (!youtubeSrc) return undefined;
    const timers = [
      window.setTimeout(() => ensurePlayback(), 80),
      window.setTimeout(() => ensurePlayback(), 250),
      window.setTimeout(() => ensurePlayback(), 500),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [activeVideo?.id, ensurePlayback, youtubeSrc]);

  const handleTouchStart = useCallback((event: ReactTouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0];
    if (!touch) return;
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  }, []);

  const handleTouchEnd = useCallback(
    (event: ReactTouchEvent<HTMLDivElement>) => {
      const start = touchStartRef.current;
      const touch = event.changedTouches[0];
      touchStartRef.current = null;
      if (!start || !touch) return;

      const deltaX = touch.clientX - start.x;
      const deltaY = touch.clientY - start.y;
      const absX = Math.abs(deltaX);
      const absY = Math.abs(deltaY);
      if (absY < 56 || absY < absX * 1.2) return;

      if (deltaY < 0) {
        nextShort("touch_swipe_up");
        return;
      }
      previousShort("touch_swipe_down");
    },
    [nextShort, previousShort],
  );

  const toggleLike = useCallback(() => {
    if (!activeVideo) return;
    setLikedVideoIds((current) => ({ ...current, [activeVideo.id]: !current[activeVideo.id] }));
    void emit("click", { action: "like_toggle" });
  }, [activeVideo, emit]);

  const toggleShare = useCallback(() => {
    if (!activeVideo) return;
    setSharedVideoIds((current) => ({ ...current, [activeVideo.id]: !current[activeVideo.id] }));
    void emit("click", { action: "share_toggle" });
  }, [activeVideo, emit]);

  useEffect(() => {
    startLogged.current = false;
    progressLogged.current = false;
    completeLogged.current = false;
    if (!activeVideo) return undefined;
    void logImpression(activeVideo, "shorts", "shorts", condition, { ...loggingContext, exposureId: exposureIdRef.current });
    return undefined;
  }, [activeVideo, condition, loggingContext]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        nextShort("arrow_down");
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        previousShort("arrow_up");
      }
      if (event.key === "Escape") {
        event.preventDefault();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [nextShort, previousShort]);

  const finalizeCurrentExposure = useCallback((reason: "timer_complete" | "pagehide") => {
    const exposureId = exposureIdRef.current;
    if (finalizedExposureIdsRef.current.has(exposureId)) return;
    finalizedExposureIdsRef.current.add(exposureId);
    actualPlayingMs(true);
    void emit("exposure_end", { reason, ...playbackDwellMetadata() });
  }, [actualPlayingMs, emit, playbackDwellMetadata]);

  useEffect(() => {
    const handlePageHide = () => finalizeCurrentExposure("pagehide");
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, [finalizeCurrentExposure]);

  useEffect(() => {
    if (!exposureEndsAt) return undefined;
    const timer = window.setTimeout(() => finalizeCurrentExposure("timer_complete"), Math.max(0, exposureEndsAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [exposureEndsAt, finalizeCurrentExposure]);

  useEffect(() => {
    if (!activeVideo) return undefined;

    function handleVisibilityChange() {
      if (document.hidden) {
        hiddenAtRef.current = Date.now();
        void emit("visibility_hidden", { hidden: true });
        return;
      }
      const hiddenDurationMs = hiddenAtRef.current ? Date.now() - hiddenAtRef.current : undefined;
      hiddenAtRef.current = null;
      void emit("visibility_visible", hiddenDurationMs ? { hidden_duration_ms: hiddenDurationMs } : undefined);
    }

    function handleBlur() {
      blurAtRef.current = Date.now();
      void emit("window_blur", { blurred: true });
    }

    function handleFocus() {
      const blurredDurationMs = blurAtRef.current ? Date.now() - blurAtRef.current : undefined;
      blurAtRef.current = null;
      void emit("window_focus", blurredDurationMs ? { blurred_duration_ms: blurredDurationMs } : undefined);
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleBlur);
    window.addEventListener("focus", handleFocus);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("focus", handleFocus);
    };
  }, [activeVideo, emit]);

  if (!activeVideo) return null;

  return (
    <section className={`fixed inset-x-0 bottom-0 ${topOffsetClass} z-50 max-w-full overflow-hidden bg-zinc-950`} aria-label="Videofeed med korte videoer" data-testid="shorts-reel">
      <article className="relative mx-auto flex h-full min-w-0 w-full max-w-[430px] items-center justify-center overflow-hidden px-0 sm:px-3" data-testid="shorts-card" data-content-pool={activeVideo.contentPool}>
        <div
          className="relative h-full max-h-full min-w-0 w-full max-w-full touch-none select-none overflow-hidden overscroll-none bg-black shadow-2xl sm:rounded-3xl"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          {youtubeSrc ? (
            <iframe
              ref={iframeRef}
              className="pointer-events-none absolute inset-0 z-0 h-full w-full"
              src={youtubeSrc}
              title={activeVideo.title}
              onLoad={() => {
                window.setTimeout(() => ensurePlayback(), 80);
                window.setTimeout(() => ensurePlayback(), 220);
              }}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
              referrerPolicy="strict-origin-when-cross-origin"
            />
          ) : (
            <video
              ref={nativeVideoRef}
              className="absolute inset-0 z-0 h-full w-full max-w-full object-contain"
              src={activeVideo.videoUrl}
              muted={false}
              autoPlay={!firstVideoStartPending}
              playsInline
              preload="auto"
              loop
              onLoadedData={ensurePlayback}
              onCanPlay={ensurePlayback}
              onPlaying={() => {
                if (playingSegmentStartedAtRef.current === null) playingSegmentStartedAtRef.current = Date.now();
                firstVideoStartPendingRef.current = false;
                setFirstVideoStartPending(false);
                if (playbackStartedAtRef.current === null) playbackStartedAtRef.current = Date.now();
                void emitStart({ startup_delay_ms: Math.max(0, Date.now() - activeShownAtRef.current) });
              }}
              onTimeUpdate={(event) => {
                const duration = event.currentTarget.duration || activeVideo.durationSeconds;
                const ratio = duration > 0 ? event.currentTarget.currentTime / duration : 0;
                if (!progressLogged.current && ratio >= 0.25) emitProgress({ percent: 25, actual_playing_ms: actualPlayingMs() });
                if (!completeLogged.current && ratio >= 0.95) emitComplete({ percent: 100, actual_playing_ms: actualPlayingMs() });
              }}
              onWaiting={() => { actualPlayingMs(true); void emit("playback_waiting", playbackDwellMetadata()); }}
              onStalled={() => { actualPlayingMs(true); void emit("playback_stalled", playbackDwellMetadata()); }}
              onPause={() => {
                if (suppressNextPauseRef.current) { suppressNextPauseRef.current = false; return; }
                actualPlayingMs(true);
                void emit("playback_pause", playbackDwellMetadata());
              }}
              onError={(event) => {
                actualPlayingMs(true);
                void emit("playback_error", { ...playbackDwellMetadata(), media_error_code: event.currentTarget.error?.code ?? null });
              }}
              onEnded={() => { actualPlayingMs(true); emitComplete({ percent: 100, actual_playing_ms: actualPlayingMs() }); }}
            />
          )}
          <button
            type="button"
            className="absolute inset-0 z-10 cursor-default touch-none bg-transparent"
            aria-label={`Afspil ${activeVideo.title}`}
            data-testid="shorts-playback-shield"
            onClick={ensurePlayback}
            onPointerDown={ensurePlayback}
          />
          {firstVideoStartPending ? (
            <button
              type="button"
              className="absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white px-6 py-3 text-base font-bold text-zinc-950 shadow-xl transition hover:bg-zinc-100 active:scale-95"
              data-testid="shorts-first-start"
              onClick={startFirstVideo}
            >
              Tryk her for at starte
            </button>
          ) : null}
          <div className="absolute right-2 top-1/2 z-20 flex -translate-y-1/2 flex-col gap-3 sm:right-3">
            <ShortsActionButton label="Like" onClick={toggleLike} active={isLiked}>
              <svg viewBox="0 0 24 24" className={`h-6 w-6 stroke-current stroke-[1.9] ${isLiked ? "fill-current" : "fill-none"}`} aria-hidden="true">
                <path d="M12 21s-6.7-4.35-9.1-8.44C1.05 9.43 2.1 5.6 5.6 4.7c2.08-.53 4.07.18 5.4 1.84 1.33-1.66 3.32-2.37 5.4-1.84 3.5.9 4.55 4.73 2.7 7.86C18.7 16.65 12 21 12 21Z" />
              </svg>
            </ShortsActionButton>
            <ShortsActionButton label="Del" onClick={toggleShare} active={isShared}>
              <svg viewBox="0 0 24 24" className={`h-6 w-6 stroke-current stroke-[1.9] ${isShared ? "fill-current" : "fill-none"}`} aria-hidden="true">
                <path d="M14 5l5 5-5 5" />
                <path d="M19 10H9a4 4 0 0 0-4 4v5" />
              </svg>
            </ShortsActionButton>
            <div className="relative z-20 flex w-16 justify-center">
              <button
                type="button"
                onClick={() => nextShort("next_button")}
                className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-black text-zinc-950 shadow-lg hover:bg-zinc-100"
                aria-label="Næste video"
                data-testid="shorts-next"
              >
                ↓
              </button>
            </div>
          </div>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/80 to-transparent p-4 pb-5 text-white sm:p-5">
            <h2 className="text-base font-bold leading-tight sm:text-lg">{activeVideo.title}</h2>
            <p className="mt-2 text-sm text-white/80">{hideViewCount ? activeVideo.channel : `${activeVideo.channel} • ${formatViews(activeVideo.views)}`}</p>
          </div>
        </div>
      </article>
    </section>
  );
}
