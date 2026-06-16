"use client";

import { useRouter } from "next/navigation";
import type { Condition, Video } from "@/lib/types";
import { ShortsReel } from "./ShortsReel";

export function ShortsRouteExperience({ videos, condition }: { videos: Video[]; condition: Condition }) {
  const router = useRouter();
  if (videos.length === 0) return null;
  return <ShortsReel videos={videos} initialIndex={0} condition={condition} onClose={() => router.push(`/?condition=${encodeURIComponent(condition)}`)} />;
}
