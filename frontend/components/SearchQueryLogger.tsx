"use client";

import { useEffect } from "react";
import { sessionId, userId } from "@/lib/analytics";
import { norstatUserId } from "@/lib/norstat";
import { readExistingStudySession } from "@/lib/study-session";
import type { Condition } from "@/lib/types";

export function SearchQueryLogger({
  query,
  condition,
  contentPool,
}: {
  query: string;
  condition: Condition;
  contentPool?: string | null;
}) {
  useEffect(() => {
    const studySession = readExistingStudySession();
    const hasNorstatPid = Boolean(studySession?.norstat_pid);
    const params = new URLSearchParams({
      q: query,
      condition,
      session_id: hasNorstatPid && studySession?.session_id ? studySession.session_id : sessionId(),
      user_id: hasNorstatPid ? norstatUserId(studySession?.norstat_pid, "") : userId(),
    });
    if (contentPool) params.set("content_pool", contentPool);
    void fetch(`/api/search?${params.toString()}`, { cache: "no-store" });
  }, [condition, contentPool, query]);

  return null;
}
