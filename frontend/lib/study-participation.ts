"use client";

import { userId } from "./analytics";
import { norstatUserId } from "./norstat";
import { assignStudyCondition, conditionForAssignment, patchStudySession, readStudySession } from "./study-session";
import type { ExperimentSession } from "./types";

export async function recordStudyParticipation(consentStatus: "accepted" | "declined", screenedReason?: string): Promise<ExperimentSession> {
  const local = readStudySession();
  const assignment = local.assignment ?? assignStudyCondition();
  const participantUserId = local.norstat_pid ? norstatUserId(local.norstat_pid, "") : userId();
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    keepalive: true,
    body: JSON.stringify({
      action: "study_participation_status",
      session_id: local.session_id ?? local.study_id,
      user_id: participantUserId,
      condition: conditionForAssignment(assignment),
      consent_status: consentStatus,
      screened_reason: screenedReason,
      norstat_pid: local.norstat_pid,
    }),
  });
  if (!response.ok) throw new Error("Kunne ikke registrere deltagelsesstatus.");
  const session = await response.json() as ExperimentSession;
  patchStudySession({ assignment, session_id: session.session_id });
  return session;
}
