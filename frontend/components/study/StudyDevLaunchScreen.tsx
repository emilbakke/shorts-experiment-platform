"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExperimentShell } from "./ExperimentShell";
import { userId } from "@/lib/analytics";
import { isClientSideDevHost } from "@/lib/dev-host";
import { clearStudySurveyArtifacts, conditionForAssignment, patchStudySession, resetStudySession, studyBasePath } from "@/lib/study-session";

export function StudyDevLaunchScreen({
  durationSeconds,
  title,
  redirectTo = "reel",
}: {
  durationSeconds: number;
  title: string;
  redirectTo?: "reel" | "entry";
}) {
  const [hasMounted, setHasMounted] = useState(false);
  const isLocalDev = isClientSideDevHost();

  useEffect(() => {
    setHasMounted(true);
  }, []);

  useEffect(() => {
    if (!hasMounted) return;
    if (!isLocalDev) return;
    clearStudySurveyArtifacts();
    const created = resetStudySession();
    const sessionId = created.study_id;
    const assignedCondition = conditionForAssignment("control");

    void fetch("/api/session", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "study_prepare",
        session_id: sessionId,
        condition: assignedCondition,
        user_id: userId(),
        reel_duration_seconds: durationSeconds,
      }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Kunne ikke starte dev-testsessionen.");
        const payload = (await response.json()) as { session_id?: string };
        patchStudySession({
          state: redirectTo === "entry" ? "entry" : "assigned",
          assignment: "control",
          session_id: payload.session_id ?? sessionId,
          started_at: new Date().toISOString(),
          completed_at: null,
        });
        const targetPath =
          redirectTo === "entry"
            ? `${studyBasePath}?duration_seconds=${durationSeconds}`
            : `${studyBasePath}/reel?duration_seconds=${durationSeconds}`;
        window.location.replace(targetPath);
      })
      .catch(() => {
        window.location.replace(studyBasePath);
      });
  }, [durationSeconds, hasMounted, isLocalDev, redirectTo]);

  if (!hasMounted) {
    return (
      <ExperimentShell
        step={1}
        title={title}
        description="Nulstiller studiesessionen og sender dig videre til en frisk test."
      >
        <div className="rounded-[2rem] border border-white/10 bg-white/6 p-6 text-sm text-white/72 shadow-2xl shadow-black/20 backdrop-blur">
          Starter testsession…
        </div>
      </ExperimentShell>
    );
  }

  if (!isLocalDev) {
    return (
      <ExperimentShell
        step={1}
        title="Udviklerlink utilgængeligt"
        description="Denne genvej virker kun lokalt på udviklingsmaskinen eller det private lokalnetværk og er ikke tilgængelig i deltagerflowet."
      >
        <div className="space-y-4 rounded-[2rem] border border-white/10 bg-white/6 p-6 text-sm text-white/72 shadow-2xl shadow-black/20 backdrop-blur">
          <p>Brug det normale study-link i stedet.</p>
          <Link
            href={studyBasePath}
            className="inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500"
          >
            Gå til undersøgelsen
          </Link>
        </div>
      </ExperimentShell>
    );
  }

  return (
    <ExperimentShell
      step={1}
      title={title}
      description="Nulstiller studiesessionen og sender dig videre til en frisk test."
    >
      <div className="rounded-[2rem] border border-white/10 bg-white/6 p-6 text-sm text-white/72 shadow-2xl shadow-black/20 backdrop-blur">
        Starter testsession…
      </div>
    </ExperimentShell>
  );
}
