import { getHomepageVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const condition = normalizeCondition(searchParams.get("condition"));
  const contentPool = searchParams.get("content_pool");
  return Response.json(await getHomepageVideos(condition, contentPool, searchParams.get("category") ?? searchParams.get("topic"), searchParams.get("session_id")));
}
