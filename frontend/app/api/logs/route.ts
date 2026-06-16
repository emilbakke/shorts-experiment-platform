import { getLogs, resetLogs } from "@/lib/server-log-store";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return Response.json(await getLogs(), {
    headers: {
      "cache-control": "no-store, no-cache, must-revalidate",
    },
  });
}

export async function DELETE() {
  return Response.json(await resetLogs(), {
    headers: {
      "cache-control": "no-store, no-cache, must-revalidate",
    },
  });
}
