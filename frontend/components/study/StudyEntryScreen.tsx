"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentShell } from "./ExperimentShell";
import { isClientSideDevHost } from "@/lib/dev-host";
import { clearStudySurveyArtifacts, incompleteReturnRoute, patchStudySession, readStudySession, resetStudySession, shouldActivateReelForReturn, studyBasePath, writeStudySession, type StudyAssignment, type StudySession, type StudyState } from "@/lib/study-session";
import { normalizeNorstatPid, norstatRedirectUrl, norstatUserId } from "@/lib/norstat";
import type { ExperimentSession } from "@/lib/types";
import { recordStudyParticipation } from "@/lib/study-participation";


function assignmentFromCondition(condition: string | null | undefined): StudyAssignment {
  return condition === "treatment_problematic_content" ? "treatment" : "control";
}

function stateFromServerSession(serverSession: ExperimentSession): StudyState {
  const state = serverSession.study_state;
  if (
    state === "pre_survey" ||
    state === "instructions" ||
    state === "assigned" ||
    state === "reel_active" ||
    state === "reel_completed" ||
    state === "post_survey" ||
    state === "complete" ||
    state === "debrief" ||
    state === "interrupted"
  ) {
    return state;
  }
  return "assigned";
}

function localSessionFromServer(serverSession: ExperimentSession, pid: string): StudySession {
  return {
    study_id: serverSession.session_id,
    state: stateFromServerSession(serverSession),
    assignment: assignmentFromCondition(serverSession.condition),
    session_id: serverSession.session_id,
    norstat_pid: pid,
    started_at: serverSession.created_at ?? null,
    completed_at: serverSession.post_survey_completed_at ?? null,
  };
}

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function StudyEntryScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [hasMounted, setHasMounted] = useState(false);
  const [researchConsent, setResearchConsent] = useState(false);
  const [error, setError] = useState("");
  const isLocalDev = isClientSideDevHost();

  const navigateWithFreshSession = useCallback(
    (durationSeconds?: number) => {
      clearStudySurveyArtifacts();
      resetStudySession();
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.delete("reset");
      if (durationSeconds && durationSeconds > 0) {
        nextParams.set("duration_seconds", String(durationSeconds));
      } else {
        nextParams.delete("duration_seconds");
      }
      const query = nextParams.toString();
      router.replace(`${studyBasePath}${query ? `?${query}` : ""}`);
    },
    [router, searchParams],
  );

  useEffect(() => {
    const mountTimer = window.setTimeout(() => setHasMounted(true), 0);
    return () => window.clearTimeout(mountTimer);
  }, []);

  useEffect(() => {
    if (searchParams.get("reset") === "1") {
      navigateWithFreshSession(Number(searchParams.get("duration_seconds") ?? "0") || undefined);
      return;
    }
    const pid = normalizeNorstatPid(searchParams.get("pid"));
    const existingSession = readStudySession();
    let session = existingSession;
    if (pid && existingSession.norstat_pid !== pid) {
      clearStudySurveyArtifacts();
      resetStudySession();
      session = patchStudySession({ norstat_pid: pid });
    }

    let cancelled = false;
    const routeFromSession = async (localSession: StudySession, serverSession?: ExperimentSession | null) => {
      try {
        const fetchedServerSession =
          serverSession ??
          (localSession.session_id
            ? await fetch(`/api/session?${new URLSearchParams({ session_id: localSession.session_id }).toString()}`).then((response) => response.json() as Promise<ExperimentSession>)
            : null);
        const refreshedServerSession = shouldActivateReelForReturn(localSession, fetchedServerSession)
          ? await fetch("/api/session", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ action: "study_reel_activate", session_id: localSession.session_id }),
            }).then((response) => response.json() as Promise<ExperimentSession>)
          : fetchedServerSession;
        if (!cancelled) {
          router.replace(`${incompleteReturnRoute(localSession, refreshedServerSession)}${suffix(searchParams)}`);
        }
      } catch {
        if (!cancelled) router.replace(`${incompleteReturnRoute(localSession)}${suffix(searchParams)}`);
      }
    };

    if (session.state !== "entry") {
      void routeFromSession(session);
      return () => {
        cancelled = true;
      };
    }

    if (pid && !searchParams.has("duration_seconds")) {
      const recoverFromBackend = async () => {
        try {
          const userId = norstatUserId(pid, "");
          const latest = await fetch(`/api/session?${new URLSearchParams({ latest_study: "1", user_id: userId }).toString()}`).then((response) => response.json() as Promise<ExperimentSession | null>);
          if (!latest || cancelled) return;
          const recoveredSession = localSessionFromServer(latest, pid);
          writeStudySession(recoveredSession);
          await routeFromSession(recoveredSession, latest);
        } catch {
          // No recoverable backend session: keep normal fresh entry behavior.
        }
      };

      void recoverFromBackend();
      return () => {
        cancelled = true;
      };
    }
  }, [navigateWithFreshSession, router, searchParams]);

  async function declineStudy() {
    const session = readStudySession();
    try { await recordStudyParticipation("declined", "declined_participation"); } catch { /* keep participant exit available */ }
    window.location.assign(norstatRedirectUrl("Screened", session.norstat_pid ?? searchParams.get("pid")));
  }

  async function startStudy() {
    if (!researchConsent) {
      setError("Du skal give samtykke for at fortsætte.");
      return;
    }

    setError("");
    window.localStorage.setItem(
      "exp-video-study-consent",
      JSON.stringify({ research_use_consent: true, consented_at: new Date().toISOString() }),
    );
    try {
      await recordStudyParticipation("accepted");
      patchStudySession({ state: "pre_survey" });
      router.push(`${studyBasePath}/pre${suffix(searchParams)}`);
    } catch (recordError) {
      setError(recordError instanceof Error ? recordError.message : "Kunne ikke registrere samtykke.");
    }
  }

  return (
    <ExperimentShell
      step={1}
      title="Undersøgelse om Shorts-videoer"
      description="Du bedes først besvare nogle få spørgsmål, se en række korte videoer, og derefter besvare nogle afsluttende spørgsmål."
    >
      <div className="space-y-5 rounded-[2rem] border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/20 backdrop-blur sm:p-6">
        <div className="space-y-3 text-sm leading-7 text-white/72">
          <p>Denne session er designet som ét sammenhængende visningsforløb.</p>
          <p>
            Det er vigtigt du bliver i videofeedet, indtil timeren udløber.{" "}
            <strong className="font-black text-white/90">Hvis der er en video, du ikke har lyst til at se, skal du bare scrolle videre til den næste.</strong>{" "}
            Du kan til enhver tid afbryde, men hvis du forlader undersøgelsen tidligt, afbrydes din deltagelse i eksperimentet.
          </p>
        </div>
        <div className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4 sm:p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/45">Forløb</p>
          <div className="mt-3 flex flex-col gap-3 text-sm text-white/78 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
            {["Baggrundsspørgsmål", "Videofeed", "Afsluttende spørgsmål", "Debriefing"].map((item, index, items) => (
              <div key={item} className="flex items-center gap-3 sm:gap-2">
                <span className="font-semibold text-white/88">{item}</span>
                {index < items.length - 1 ? (
                  <span className="text-white/35" aria-hidden="true">
                    →
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-3 rounded-[1.5rem] border border-white/10 bg-black/20 p-4 text-sm leading-6 text-white/78">
          <p className="font-semibold text-white/82">Samtykkeerklæring</p>
          <p>
            Du inviteres til at deltage i et forskningsprojekt ved Syddansk Universitet om korte videoer og holdninger. Deltagelse er frivillig. Du besvarer spørgsmål før og efter et 4 minutters videofeed, og dine svar bruges kun til forskning.
          </p>
          <p>
            Vi behandler almindelige personoplysninger som dine spørgeskemasvar, tekniske sessionsoplysninger og information om hvilke videoer der vises og interageres med. Data behandles fortroligt og pseudonymiseres i analysen; resultater rapporteres kun samlet, så enkeltpersoner ikke kan genkendes.
          </p>
          <p>
            Behandlingsgrundlaget er dit samtykke, jf. GDPR artikel 6, stk. 1, litra a, for almindelige personoplysninger. Data opbevares på SDU/UCloud-infrastruktur med adgang begrænset til autoriserede forskere i projektet og behandles efter SDU/DDC’s interne sikkerhedsprocedurer.
          </p>
          <p>
            Du kan afbryde deltagelsen når som helst uden begrundelse, og du kan senere trække dit samtykke tilbage. Har du spørgsmål, kan du kontakte os på emilbj@sam.sdu.dk.
          </p>
          <label className="flex gap-3 font-medium text-white/86">
            <input
              type="checkbox"
              checked={researchConsent}
              onChange={(event) => setResearchConsent(event.target.checked)}
              className="mt-1 h-5 w-5 shrink-0 accent-red-600"
              data-testid="study-entry-consent"
            />
            <span>Jeg giver samtykke til at mine svar bruges til forskning i overensstemmelse med ovenstående information.</span>
          </label>
          <label className={`flex gap-3 rounded-2xl border p-3 font-semibold transition ${researchConsent ? "cursor-not-allowed border-white/10 bg-white/5 text-white/35" : "cursor-pointer border-red-500/45 bg-red-600/12 text-red-100 hover:bg-red-600/20"}`}>
            <input
              type="checkbox"
              checked={false}
              disabled={researchConsent}
              onChange={(event) => {
                if (event.target.checked) void declineStudy();
              }}
              className="mt-1 h-5 w-5 shrink-0 accent-red-600"
              data-testid="study-entry-decline"
            />
            <span>Jeg ønsker ikke at deltage i studiet.</span>
          </label>
        </div>

        {error ? <p className="rounded-2xl bg-red-500/12 px-4 py-3 text-sm font-medium text-red-200">{error}</p> : null}

        <button
          type="button"
          onClick={startStudy}
          className="inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500"
          data-testid="study-entry-start"
        >
          Start undersøgelsen
        </button>
        {hasMounted && isLocalDev ? (
          <div className="rounded-[1.5rem] border border-dashed border-white/15 bg-black/10 p-4 text-sm text-white/68">
            <p className="font-semibold text-white/82">Lokal udviklertilstand</p>
            <p className="mt-2">Brug disse knapper til hurtigt at nulstille studiesessionen og teste reel-længden uden at blive sendt videre af gammel state.</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => navigateWithFreshSession()}
                className="inline-flex h-11 items-center justify-center rounded-full border border-white/15 bg-white/8 px-4 text-sm font-semibold text-white transition hover:bg-white/14"
              >
                Nulstil testsession
              </button>
              <button
                type="button"
                onClick={() => navigateWithFreshSession(60)}
                className="inline-flex h-11 items-center justify-center rounded-full border border-red-500/30 bg-red-600/15 px-4 text-sm font-semibold text-white transition hover:bg-red-600/25"
              >
                Start 60 sek. test
              </button>
              <Link
                href={`${studyBasePath}/dev-flow-60`}
                className="inline-flex h-11 items-center justify-center rounded-full border border-white/15 bg-white/8 px-4 text-sm font-semibold text-white transition hover:bg-white/14"
              >
                Vis helt 60 sek. flow
              </Link>
              <Link
                href={`${studyBasePath}/dev-60`}
                className="inline-flex h-11 items-center justify-center rounded-full border border-white/15 bg-white/8 px-4 text-sm font-semibold text-white transition hover:bg-white/14"
              >
                Åbn reel-only dev-link
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </ExperimentShell>
  );
}
