import { getShortsVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  return Response.json(await getShortsVideos(normalizeCondition(searchParams.get("condition")), searchParams.get("content_pool"), searchParams.get("session_id")));
}
