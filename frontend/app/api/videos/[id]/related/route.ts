import { getRelatedVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  return Response.json(await getRelatedVideos(id, normalizeCondition(searchParams.get("condition")), searchParams.get("content_pool"), searchParams.get("session_id")));
}
