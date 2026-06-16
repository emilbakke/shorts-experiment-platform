"use client";

import { formatViews } from "@/lib/video-utils";
import type { Video } from "@/lib/types";

export function ShortsCard({ video, onOpen }: { video: Video; onOpen: () => void }) {
  const hasThumbnail = video.thumbnailUrl && !video.thumbnailUrl.startsWith("gradient://");

  return (
    <article
      className="w-[150px] shrink-0 sm:w-[170px]"
      data-testid="shorts-shelf-card"
      data-content-pool={video.contentPool}
      data-source={video.source ?? ""}
      data-youtube-id={video.youtubeId ?? ""}
    >
      <button type="button" onClick={onOpen} className="group block w-full text-left" aria-label={`Åbn kort video: ${video.title}`}>
        <div className="relative aspect-[9/16] overflow-hidden rounded-2xl bg-gradient-to-br from-zinc-950 via-zinc-800 to-red-600 shadow-sm">
          {hasThumbnail ? <img src={video.thumbnailUrl} alt="" className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105" /> : null}
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 p-3 text-white">
            <p className="line-clamp-2 text-sm font-bold leading-tight">{video.title}</p>
            <p className="mt-1 text-xs text-white/80">{formatViews(video.views)}</p>
          </div>
        </div>
      </button>
    </article>
  );
}
