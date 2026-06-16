import type { Video } from "./types";

export function topicSimilarity(video: Video, topic?: string): number {
  if (!topic) return 0.5;
  return video.topic === topic ? 1 : 0.2;
}

export function recommendationScore(video: Video, topic?: string): number {
  return topicSimilarity(video, topic) + video.popularityScore + video.freshnessScore;
}

export function rankForHomepage(videos: Video[]): Video[] {
  return [...videos]
    .filter((video) => !video.isShort)
    .sort((a, b) => recommendationScore(b) - recommendationScore(a))
    .map((video, index) => ({ ...video, rank: index + 1 }));
}

export function rankForRelated(videos: Video[], source: Video): Video[] {
  return [...videos]
    .filter((video) => !video.isShort && video.id !== source.id)
    .sort((a, b) => recommendationScore(b, source.topic) - recommendationScore(a, source.topic))
    .map((video, index) => ({ ...video, rank: index + 1 }));
}

export function rankForShorts(videos: Video[]): Video[] {
  return [...videos]
    .filter((video) => video.isShort)
    .sort((a, b) => recommendationScore(b) - recommendationScore(a))
    .map((video, index) => ({ ...video, rank: index + 1 }));
}
