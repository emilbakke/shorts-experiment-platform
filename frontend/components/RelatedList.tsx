import type { Condition, Video } from "@/lib/types";
import { VideoCard } from "./VideoCard";

export function RelatedList({ videos, condition }: { videos: Video[]; condition: Condition }) {
  return (
    <aside className="w-full space-y-3 lg:w-[30%]" aria-label="Relaterede videoer">
      <h2 className="text-lg font-semibold text-zinc-950">Relaterede videoer</h2>
      <div className="grid grid-cols-1 gap-4">
        {videos.map((video) => (
          <VideoCard key={video.id} video={video} surface="related" clickFrom="related" condition={condition} />
        ))}
      </div>
    </aside>
  );
}
