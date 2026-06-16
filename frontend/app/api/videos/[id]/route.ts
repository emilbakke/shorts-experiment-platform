import { getVideo } from "@/lib/data";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const video = await getVideo(id);
  if (!video) return Response.json({ error: "video not found" }, { status: 404 });
  return Response.json(video);
}
