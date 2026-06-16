export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const token = request.headers.get("x-viewtube-monitor-token");
  const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
  const query = new URL(request.url).search;
  const response = await fetch(`${backendUrl}/study/monitor${query}`, {
    headers: token ? { "x-viewtube-monitor-token": token } : {},
    cache: "no-store",
  });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
