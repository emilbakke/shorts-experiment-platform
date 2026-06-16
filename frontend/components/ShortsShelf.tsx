"use client";

import { useState } from "react";
import type { Condition, Video } from "@/lib/types";
import { payloadFor, sendJsonNow } from "@/lib/analytics";
import { ShortsCard } from "./ShortsCard";
import { ShortsReel } from "./ShortsReel";

export function ShortsShelf({ videos, condition }: { videos: Video[]; condition: Condition }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (videos.length === 0) return null;

  function openShort(video: Video, index: number) {
    setOpenIndex(index);
    void (async () => {
      const payload = payloadFor(video, "shorts", "shorts", condition);
      await sendJsonNow("/api/impressions", payload);
      await sendJsonNow("/api/events", { ...payload, event_type: "click", metadata: { action: "open_reel", shelf_index: index } });
    })();
  }

  return (
    <section className="mb-5 border-b border-zinc-100 pb-4" aria-label="Korte videoer" data-testid="shorts-shelf">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xl font-bold text-zinc-950">Korte videoer</h2>
      </div>
      <div className="flex gap-4 overflow-x-auto pb-2" aria-label="Forhåndsvisninger af korte videoer">
        {videos.map((video, index) => (
          <ShortsCard key={video.id} video={video} onOpen={() => openShort(video, index)} />
        ))}
      </div>
      {openIndex !== null ? <ShortsReel videos={videos} initialIndex={openIndex} condition={condition} onClose={() => setOpenIndex(null)} /> : null}
    </section>
  );
}
