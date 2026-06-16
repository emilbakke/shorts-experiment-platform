import type { Condition, Video } from "@/lib/types";
import { VideoCard } from "./VideoCard";
import { SearchQueryLogger } from "./SearchQueryLogger";

export function SearchResultsList({
  videos,
  query,
  condition,
  contentPool,
}: {
  videos: Video[];
  query: string;
  condition: Condition;
  contentPool?: string | null;
}) {
  return (
    <section aria-label="Søgeresultater" className="space-y-4">
      <SearchQueryLogger query={query} condition={condition} contentPool={contentPool} />
      <h1 className="text-xl font-semibold text-zinc-950">Søgeresultater for “{query || "alle videoer"}”</h1>
      <div className="grid max-w-5xl grid-cols-1 gap-4">
        {videos.map((video) => (
          <VideoCard key={video.id} video={video} surface="search" clickFrom="search" condition={condition} />
        ))}
      </div>
    </section>
  );
}
