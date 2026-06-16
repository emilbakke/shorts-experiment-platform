import { addImpression } from "@/lib/server-log-store";
import type { LogPayload } from "@/lib/types";

function withUserId(payload: Record<string, unknown>): Record<string, unknown> {
  return { user_id: payload.user_id || payload.session_id || "anonymous-user", ...payload };
}

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    return Response.json(await addImpression(withUserId(payload) as LogPayload));
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "invalid impression" }, { status: 400 });
  }
}
