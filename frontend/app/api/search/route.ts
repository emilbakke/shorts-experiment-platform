import { backendAction } from "@/lib/backend-bridge";
import { normalizeCondition } from "@/lib/experiment";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q") ?? "";
  const condition = normalizeCondition(searchParams.get("condition"));
  const payload = await backendAction("search", {
    q: query,
    condition,
    content_pool: searchParams.get("content_pool"),
    session_id: searchParams.get("session_id") ?? undefined,
    user_id: searchParams.get("user_id") ?? undefined,
  });
  return Response.json(payload);
}
