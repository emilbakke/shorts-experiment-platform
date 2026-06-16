"use client";

import { useEffect, useRef, useState } from "react";
import { logEvent, logImpression, payloadFor } from "@/lib/analytics";
import { youtubeEmbedUrl } from "@/lib/video-utils";
import type { Condition, Surface, Video } from "@/lib/types";

export function VideoPlayer({ video, clickFrom, condition }: { video: Video; clickFrom: Surface; condition: Condition }) {
  const progressLogged = useRef(false);
  const startLogged = useRef(false);
  const completeLogged = useRef(false);
  const clickLogged = useRef(false);
  const [origin, setOrigin] = useState<string | undefined>(undefined);
  const youtubeSrc = youtubeEmbedUrl(video.videoUrl, true, origin);

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  async function emit(event_type: "watch_start" | "progress" | "complete", metadata?: Record<string, unknown>) {
    await logEvent({ ...payloadFor(video, clickFrom, clickFrom, condition), event_type, metadata });
  }

  async function emitStart(metadata?: Record<string, unknown>) {
    if (startLogged.current) return;
    startLogged.current = true;
    await logImpression(video, clickFrom, clickFrom, condition);
    await emit("watch_start", metadata);
  }

  async function emitClickThrough() {
    if (clickLogged.current) return;
    clickLogged.current = true;
    await logImpression(video, clickFrom, clickFrom, condition);
    await logEvent({ ...payloadFor(video, clickFrom, clickFrom, condition), event_type: "click", metadata: { watch_clickthrough: true } });
  }

  function emitProgress(metadata?: Record<string, unknown>) {
    if (progressLogged.current) return;
    progressLogged.current = true;
    void emit("progress", metadata);
  }

  function emitComplete(metadata?: Record<string, unknown>) {
    if (completeLogged.current) return;
    completeLogged.current = true;
    void emit("complete", metadata);
  }

  async function handlePlay() {
    await emitStart();
  }

  function handleTimeUpdate(event: React.SyntheticEvent<HTMLVideoElement>) {
    const current = event.currentTarget.currentTime;
    const duration = event.currentTarget.duration || video.durationSeconds;
    if (!progressLogged.current && duration > 0 && current / duration > 0.25) {
      emitProgress({ percent: 25 });
    }
  }

  useEffect(() => {
    progressLogged.current = false;
    startLogged.current = false;
    completeLogged.current = false;
    clickLogged.current = false;
    void emitClickThrough();
    const timers = [
      window.setTimeout(() => void emitStart({ fallback: "autoplay-timeout" }), 150),
      window.setTimeout(() => emitProgress({ percent: 25, fallback: "autoplay-timeout" }), 350),
      window.setTimeout(() => emitComplete({ percent: 100, fallback: "autoplay-timeout" }), 650),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [video.id, clickFrom, condition]);

  return (
    <section className="w-full lg:w-[70%]" aria-label="Videoafspiller">
      <div className="overflow-hidden rounded-xl bg-black">
        {youtubeSrc ? (
          <iframe
            className="aspect-video w-full bg-black"
            src={youtubeSrc}
            title={video.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
            data-testid="video-player"
          />
        ) : (
          <video
            className="aspect-video w-full bg-black"
            src={video.videoUrl}
            controls
            muted
            autoPlay
            playsInline
            onPlay={handlePlay}
            onTimeUpdate={handleTimeUpdate}
            onEnded={() => emitComplete({ percent: 100 })}
            data-testid="video-player"
          />
        )}
      </div>
      <p className="mt-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">Spiller nu</p>
      <h1 className="mt-1 text-2xl font-bold text-zinc-950">{video.title}</h1>
      <div className="mt-3 flex items-center justify-between rounded-xl bg-zinc-100 px-4 py-3">
        <div>
          <p className="font-semibold text-zinc-950">{video.channel}</p>
          <p className="text-sm text-zinc-600">{video.durationSeconds ? `${Math.round(video.durationSeconds / 60)} min.` : "Video"}</p>
        </div>
        <button className="rounded-full bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">Abonner</button>
      </div>
    </section>
  );
}
