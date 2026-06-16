import { getHomepageBundle } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";
import { VideoCard } from "@/components/VideoCard";
import { ShortsShelf } from "@/components/ShortsShelf";
import { CategoryFilterChips } from "@/components/CategoryFilterChips";

export default async function Home({ searchParams }: { searchParams: Promise<{ condition?: string; content_pool?: string; category?: string; session_id?: string }> }) {
  const params = await searchParams;
  const condition = normalizeCondition(params.condition);
  const { shorts, videos, topics } = await getHomepageBundle(condition, params.content_pool, params.category, params.session_id);
  return (
    <section className="px-4 py-4 md:px-6" aria-label="Anbefalet startside" data-testid="home-condition" data-condition={condition}>
      <ShortsShelf videos={shorts} condition={condition} />
      <CategoryFilterChips topics={topics} selected={params.category} condition={condition} contentPool={params.content_pool} sessionId={params.session_id} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="home-grid">
        {videos.map((video) => (
          <VideoCard key={video.id} video={video} surface="recommendation" clickFrom="recommendation" condition={condition} />
        ))}
      </div>
    </section>
  );
}
