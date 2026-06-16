"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { formatDuration, formatViews } from "@/lib/video-utils";
import { logEvent, logImpression, payloadFor } from "@/lib/analytics";
import type { Condition, EventPayload, Surface, Video } from "@/lib/types";

const gradients = [
  "from-red-500 via-orange-400 to-yellow-300",
  "from-blue-600 via-cyan-500 to-emerald-300",
  "from-fuchsia-600 via-purple-500 to-indigo-400",
  "from-zinc-800 via-slate-600 to-zinc-400",
];

export function VideoCard({
  video,
  surface,
  clickFrom = surface,
  condition,
}: {
  video: Video;
  surface: Surface;
  clickFrom?: Surface;
  condition: Condition;
}) {
  const logged = useRef(false);

  useEffect(() => {
    if (!logged.current) {
      logged.current = true;
      void logImpression(video, surface, clickFrom, condition);
    }
  }, [clickFrom, condition, surface, video]);

  const gradient = gradients[(video.rank ?? 1) % gradients.length];
  const hasThumbnail = video.thumbnailUrl && !video.thumbnailUrl.startsWith("gradient://");
  const routeId = video.routeId ?? video.id;
  const query = new URLSearchParams({ from: clickFrom, condition });
  const href = `/watch/${encodeURIComponent(routeId)}?${query.toString()}`;

  function handleClick() {
    const payload: EventPayload = {
      ...payloadFor(video, surface, clickFrom, condition),
      event_type: "click",
      metadata: { card_click: true, watch_clickthrough: true },
    };
    void logEvent(payload);
  }

  return (
    <article className="group cursor-pointer" data-testid="video-card" data-content-pool={video.contentPool} data-source={video.source ?? ""} data-youtube-id={video.youtubeId ?? ""}>
      <Link href={href} prefetch onClick={handleClick} role="button" className="block w-full text-left" aria-label={`Se ${video.title}`} data-href={href}>
        <div className={`relative aspect-video overflow-hidden rounded-xl bg-gradient-to-br ${gradient}`}>
          {hasThumbnail ? <img src={video.thumbnailUrl} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105" /> : null}
          <div className="absolute inset-0 bg-black/10" />
          <div className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-xs font-semibold text-white">{formatDuration(video.durationSeconds)}</div>
        </div>
        <div className="mt-2 flex gap-3">
          <div className="mt-1 h-9 w-9 shrink-0 rounded-full bg-zinc-300" />
          <div className="min-w-0">
            <h3 className="line-clamp-2 text-sm font-semibold leading-5 text-zinc-950 group-hover:text-blue-700">{video.title}</h3>
            <p className="mt-1 text-sm text-zinc-600">{video.channel}</p>
            <p className="text-sm text-zinc-600">{formatViews(video.views)} • for nylig</p>
          </div>
        </div>
      </Link>
    </article>
  );
}
