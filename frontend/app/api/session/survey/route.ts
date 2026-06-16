import { submitEntrySurvey } from "@/lib/server-log-store";
import type { EntrySurveyPayload } from "@/lib/types";

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as EntrySurveyPayload;
    return Response.json(await submitEntrySurvey(payload));
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "invalid survey" }, { status: 400 });
  }
}
