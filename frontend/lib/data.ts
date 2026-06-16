import type { Condition, ContentPool, PoolMode, Surface, Video } from "./types";
import { defaultCondition, normalizeCondition } from "./experiment";
import { backendAction } from "./backend-bridge";

type BackendVideo = {
  id: string;
  route_id?: string;
  title: string;
  content_pool: ContentPool;
  channel: string;
  topic: string;
  thumbnail_url: string;
  video_url: string;
  duration_seconds: number;
  views: number;
  popularity_score: number;
  freshness_score: number;
  is_short: boolean;
  rank?: number;
  youtube_id?: string | null;
  source?: string | null;
};

type SearchPayload = { query: string; condition?: Condition; results: BackendVideo[] };
type WatchPayload = { video: BackendVideo | null; related: BackendVideo[] };
type HomepageBundlePayload = { shorts: BackendVideo[]; videos: BackendVideo[]; topics: string[] };

const demoAliases: Record<string, string> = {
  v1: "Neon City Walkthrough in 4K",
  v2: "How Recommendation Systems Rank Videos",
  v3: "Street Food Tour: Night Market Classics",
  v4: "Build a Cozy Desk Setup from Scratch",
  v5: "Morning Focus Music for Deep Work",
  v6: "Beginner Camera Moves That Feel Cinematic",
  v7: "Tiny Apartment Makeover Timelapse",
  v8: "One-Day Train Trip Along the Coast",
  s1: "60-Second Pasta Trick",
  s2: "Desk Cable Cleanup Hack",
  s3: "City Sunrise Hyperlapse",
  s4: "AI Term Explained Fast",
};

function versionedStudyMediaUrl(url: string): string {
  if (!url.startsWith("/api/study/media/")) return url;
  const version = process.env.NEXT_PUBLIC_VIEWTUBE_MEDIA_VERSION || "ios-h264-aac-20260603";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}media_v=${encodeURIComponent(version)}`;
}

export function toVideo(row: BackendVideo): Video {
  return {
    id: row.id,
    routeId: row.route_id ?? `v-${row.id}`,
    title: row.title,
    contentPool: row.content_pool,
    channel: row.channel,
    topic: row.topic,
    thumbnailUrl: row.thumbnail_url,
    videoUrl: versionedStudyMediaUrl(row.video_url),
    durationSeconds: row.duration_seconds,
    views: row.views,
    popularityScore: row.popularity_score,
    freshnessScore: row.freshness_score,
    isShort: row.is_short,
    rank: row.rank,
    youtubeId: row.youtube_id ?? undefined,
    source: row.source ?? undefined,
  };
}

function videosFromRows(rows: BackendVideo[]): Video[] {
  return rows.map(toVideo);
}

export async function getHomepageVideos(
  condition: Condition = defaultCondition,
  requestedPool?: string | null,
  category?: string | null,
  session?: string | null,
): Promise<Video[]> {
  const effectiveCondition = normalizeCondition(condition);
  return videosFromRows(
    await backendAction<BackendVideo[]>("homepage", {
      condition: effectiveCondition,
      content_pool: requestedPool,
      category,
      session_id: session,
    }),
  );
}

export async function getShortsVideos(condition: Condition = defaultCondition, requestedPool?: string | null, session?: string | null): Promise<Video[]> {
  const effectiveCondition = normalizeCondition(condition);
  return videosFromRows(await backendAction<BackendVideo[]>("shorts", { condition: effectiveCondition, content_pool: requestedPool, session_id: session }));
}

export async function getStudyShortsVideos(condition: Condition = defaultCondition, session?: string | null): Promise<Video[]> {
  const effectiveCondition = normalizeCondition(condition);
  return videosFromRows(await backendAction<BackendVideo[]>("study_shorts", { condition: effectiveCondition, session_id: session }));
}

export async function getHomepageBundle(
  condition: Condition = defaultCondition,
  requestedPool?: string | null,
  category?: string | null,
  session?: string | null,
): Promise<{ shorts: Video[]; videos: Video[]; topics: string[] }> {
  const effectiveCondition = normalizeCondition(condition);
  const payload = await backendAction<HomepageBundlePayload>("homepage_bundle", {
    condition: effectiveCondition,
    content_pool: requestedPool,
    category,
    session_id: session,
  });
  return {
    shorts: videosFromRows(payload.shorts),
    videos: videosFromRows(payload.videos),
    topics: payload.topics,
  };
}

export async function getVideo(id: string): Promise<Video | undefined> {
  const decoded = decodeURIComponent(id);
  const row = await backendAction<BackendVideo | null>("video", { video_id: decoded });
  if (row) return toVideo(row);

  const aliasTitle = demoAliases[decoded];
  if (!aliasTitle) return undefined;
  const rows = await backendAction<BackendVideo[]>("all_videos");
  const alias = rows.find((candidate) => candidate.title === aliasTitle);
  return alias ? toVideo(alias) : undefined;
}

export async function getRelatedVideos(id: string, condition: Condition = defaultCondition, requestedPool?: string | null, session?: string | null): Promise<Video[]> {
  const effectiveCondition = normalizeCondition(condition);
  return videosFromRows(await backendAction<BackendVideo[]>("related", { video_id: decodeURIComponent(id), condition: effectiveCondition, content_pool: requestedPool, session_id: session }));
}

export async function getWatchPayload(
  id: string,
  condition: Condition = defaultCondition,
  requestedPool?: string | null,
  session?: string | null,
): Promise<{ video?: Video; related: Video[] }> {
  const effectiveCondition = normalizeCondition(condition);
  const payload = await backendAction<WatchPayload>("watch", {
    video_id: decodeURIComponent(id),
    condition: effectiveCondition,
    content_pool: requestedPool,
    session_id: session,
  });
  return {
    video: payload.video ? toVideo(payload.video) : undefined,
    related: videosFromRows(payload.related),
  };
}

export async function searchVideos(query: string, condition: Condition = defaultCondition, requestedPool?: string | null): Promise<Video[]> {
  const effectiveCondition = normalizeCondition(condition);
  const payload = await backendAction<SearchPayload>("search_results", { q: query, condition: effectiveCondition, content_pool: requestedPool });
  return videosFromRows(payload.results);
}

export async function getCategoryTopics(condition: Condition = defaultCondition, requestedPool?: string | null): Promise<string[]> {
  const effectiveCondition = normalizeCondition(condition);
  return backendAction<string[]>("topics", { condition: effectiveCondition, content_pool: requestedPool });
}

export type { PoolMode, Surface };
