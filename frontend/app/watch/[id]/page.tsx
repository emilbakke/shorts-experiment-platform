import { notFound } from "next/navigation";
import { getWatchPayload } from "@/lib/data";
import { normalizeCondition, validSurface } from "@/lib/experiment";
import { RelatedList } from "@/components/RelatedList";
import { VideoPlayer } from "@/components/VideoPlayer";

export default async function WatchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ from?: string; condition?: string; content_pool?: string; session_id?: string }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const condition = normalizeCondition(query.condition);
  const { video, related } = await getWatchPayload(id, condition, query.content_pool, query.session_id);
  if (!video) notFound();
  const clickFrom = validSurface(query.from);
  return (
    <div className="flex flex-col gap-5 px-4 py-5 lg:flex-row lg:px-6" data-testid="watch-condition" data-condition={condition}>
      <VideoPlayer video={video} clickFrom={clickFrom} condition={condition} />
      <RelatedList videos={related} condition={condition} />
    </div>
  );
}
