import { addEvent, addImpression } from "@/lib/server-log-store";
import type { EventPayload, LogPayload } from "@/lib/types";

function withUserId(payload: Record<string, unknown>): Record<string, unknown> {
  return { user_id: payload.user_id || payload.session_id || "anonymous-user", ...payload };
}

export async function POST(request: Request) {
  const raw = await request.json().catch(() => ({}));
  const payload = withUserId(raw);
  try {
    return Response.json(await addEvent(payload as EventPayload));
  } catch (error) {
    const metadata = payload.metadata as Record<string, unknown> | undefined;
    if (payload.event_type === "click" && metadata?.watch_clickthrough === true) {
      try {
        await addImpression(payload as LogPayload);
        return Response.json(await addEvent(payload as EventPayload));
      } catch (repairError) {
        return Response.json({ error: repairError instanceof Error ? repairError.message : "invalid event" }, { status: 400 });
      }
    }
    return Response.json({ error: error instanceof Error ? error.message : "invalid event" }, { status: 400 });
  }
}
