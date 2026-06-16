import { getShortsVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";
import { ShortsRouteExperience } from "@/components/ShortsRouteExperience";

export default async function ShortsPage({ searchParams }: { searchParams: Promise<{ condition?: string; content_pool?: string; session_id?: string }> }) {
  const params = await searchParams;
  const condition = normalizeCondition(params.condition);
  const shorts = await getShortsVideos(condition, params.content_pool, params.session_id);
  return <ShortsRouteExperience videos={shorts} condition={condition} />;
}
