import { getStudyShortsVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const sessionId = searchParams.get("session_id");
    return Response.json(await getStudyShortsVideos(normalizeCondition(searchParams.get("condition")), sessionId));
  } catch (error) {
    const status = (error as Error & { status?: number }).status ?? 500;
    return Response.json({ error: error instanceof Error ? error.message : "study shorts request failed" }, { status });
  }
}
