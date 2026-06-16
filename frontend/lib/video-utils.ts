import type { Condition, Surface, Video } from "./types";
import { defaultCondition } from "./experiment";

export function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)} mio. visninger`;
  if (views >= 1_000) return `${Math.round(views / 1_000)} t. visninger`;
  return `${views} visninger`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function watchHref(video: Video, clickFrom: Surface, condition: Condition = defaultCondition): string {
  const routeId = video.routeId ?? video.id;
  return `/watch/${encodeURIComponent(routeId)}?from=${clickFrom}&condition=${condition}`;
}

export function youtubeEmbedUrl(url: string, autoplay = true, origin?: string, loop = false, startMuted = false): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    let id = "";
    if (host === "youtu.be") {
      id = parsed.pathname.slice(1);
    } else if (host === "youtube.com" || host === "m.youtube.com" || host === "music.youtube.com") {
      if (parsed.pathname.startsWith("/shorts/")) id = parsed.pathname.split("/")[2] ?? "";
      else if (parsed.pathname.startsWith("/embed/")) id = parsed.pathname.split("/")[2] ?? "";
      else id = parsed.searchParams.get("v") ?? "";
    }
    if (!id) return null;
    const params = new URLSearchParams({
      enablejsapi: "1",
      rel: "0",
      modestbranding: "1",
      playsinline: "1",
      controls: "0",
      disablekb: "1",
      fs: "0",
      iv_load_policy: "3",
      mute: startMuted ? "1" : "0",
      showinfo: "0",
    });
    if (autoplay) params.set("autoplay", "1");
    if (origin) params.set("origin", origin);
    if (loop) {
      params.set("loop", "1");
      params.set("playlist", id);
    }
    return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?${params.toString()}`;
  } catch {
    return null;
  }
}
