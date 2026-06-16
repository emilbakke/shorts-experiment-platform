"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentShell } from "./ExperimentShell";
import { incompleteReturnRoute, patchStudySession, readStudySession, resetStudySession, shouldActivateReelForReturn, studyBasePath } from "@/lib/study-session";
import type { ExperimentSession } from "@/lib/types";
import { norstatRedirectUrl, normalizeNorstatPid } from "@/lib/norstat";

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function StudyDebriefContent() {
  return (
    <div className="space-y-4 text-base leading-7 text-white/78">
      <p>
        Denne undersøgelse handler overordnet om, hvordan mennesker reagerer på forskellige typer korte videoer i et kontrolleret videomiljø, og hvordan sådan eksponering kan hænge sammen med opmærksomhed, vurderinger og holdninger efterfølgende.
      </p>
      <p>
        Vi oplyste ikke alle detaljer om de præcise hypoteser på forhånd, fordi fuld information kunne have påvirket både seeradfærd og svar i spørgeskemaet. Formålet med denne begrænsede tilbageholdelse var at mindske bias og gøre resultaterne mere retvisende.
      </p>
      <p>
        De holdninger eller synspunkter, som måtte være blevet udtrykt i videoerne, afspejler ikke forskergruppens egne holdninger. Videoerne indgår alene som forskningsmateriale i undersøgelsen.
      </p>
      <p>
        Dine data vil blive brugt til forskning om videoadfærd, holdninger og opfattelser i forbindelse med online indhold. Data analyseres på gruppeniveau og behandles i overensstemmelse med gældende databeskyttelsesregler og SDU&apos;s procedurer.
      </p>
      <p>
        Hvis det er muligt inden for projektets databeskyttelsesramme, kan du efterfølgende anmode om at få dine data slettet. Hvis du har spørgsmål til undersøgelsen eller ønsker at høre om mulighederne for tilbagetrækning af data, bedes du kontakte forskergruppen via de kontaktoplysninger, du har modtaget i deltagerinformationen.
      </p>
    </div>
  );
}

export function StudyDebriefScreen({ completionOnly = false }: { completionOnly?: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [norstatReturnUrl, setNorstatReturnUrl] = useState<string | null>(null);
  const [isCompleted, setIsCompleted] = useState(false);
  const [canShowDebrief, setCanShowDebrief] = useState(false);

  useEffect(() => {
    const session = readStudySession();
    const pid = normalizeNorstatPid(searchParams.get("pid")) ?? session.norstat_pid;

    if (!session.session_id) {
      router.replace(`${studyBasePath}${suffix(searchParams)}`);
      return;
    }

    let cancelled = false;
    const routeOrShowDebrief = async () => {
      try {
        const sessionResponse = await fetch(`/api/session?${new URLSearchParams({ session_id: session.session_id ?? "" }).toString()}`);
        const serverSession = (await sessionResponse.json()) as ExperimentSession;
        const refreshedServerSession = shouldActivateReelForReturn(session, serverSession)
          ? await fetch("/api/session", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ action: "study_reel_activate", session_id: session.session_id }),
            }).then((response) => response.json() as Promise<ExperimentSession>)
          : serverSession;

        if (cancelled) return;
        if (refreshedServerSession.study_state === "complete") {
          setIsCompleted(true);
          setCanShowDebrief(true);
          if (pid) setNorstatReturnUrl(norstatRedirectUrl("Complete", pid));
          return;
        }

        const returnRoute = incompleteReturnRoute(session, refreshedServerSession);
        if (completionOnly) {
          router.replace(`${returnRoute}${suffix(searchParams)}`);
          return;
        }

        if (returnRoute !== `${studyBasePath}/debrief`) {
          router.replace(`${returnRoute}${suffix(searchParams)}`);
          return;
        }
        if (session.state !== "debrief") {
          patchStudySession({ state: "debrief" });
        }
        setCanShowDebrief(true);
      } catch {
        if (completionOnly) router.replace(`${studyBasePath}${suffix(searchParams)}`);
      }
    };

    void routeOrShowDebrief();
    return () => {
      cancelled = true;
    };
  }, [completionOnly, router, searchParams]);

  if (!canShowDebrief) {
    return (
      <section className="flex min-h-screen items-center justify-center bg-zinc-950 text-white">
        <div className="rounded-3xl border border-white/10 bg-white/6 px-6 py-5 text-sm text-white/72 shadow-2xl">Indlæser studiesessionen…</div>
      </section>
    );
  }

  const title = isCompleted ? "Tak for din deltagelse" : "Information om undersøgelsen";
  const description = isCompleted
    ? "Din videosession er nu afsluttet. Læs venligst informationen nedenfor, før du afslutter undersøgelsen."
    : "Du har afbrudt deltagelsen. Du får stadig den samme information om undersøgelsens formål som ved afslutningen.";

  return (
    <ExperimentShell step={4} title={title} description={description}>
      <div className="space-y-6 rounded-[2rem] border border-white/10 bg-white/6 p-6 shadow-2xl shadow-black/20 backdrop-blur">
        {norstatReturnUrl ? (
          <div className="rounded-[1.5rem] border border-red-500/40 bg-red-600/15 p-4 text-sm leading-6 text-red-50">
            <p className="font-semibold text-white">Vigtigt: Afslut via Norstat</p>
            <p className="mt-2">
              For at din deltagelse kan registreres korrekt, skal du trykke på knappen “Afslut”. Knappen sender dig tilbage til Norstat og markerer undersøgelsen som gennemført.
            </p>
            <a
              href={norstatReturnUrl}
              className="mt-4 inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500"
              data-testid="norstat-complete-redirect"
            >
              Afslut
            </a>
          </div>
        ) : null}
        <StudyDebriefContent />
        <div className="flex flex-wrap gap-3">
          {isCompleted && !norstatReturnUrl ? (
            <Link
              href={`${studyBasePath}${suffix(searchParams)}`}
              onClick={() => resetStudySession()}
              className="inline-flex h-12 items-center justify-center rounded-full bg-white px-6 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-200"
            >
              Start en ny testsession
            </Link>
          ) : null}
        </div>
      </div>
    </ExperimentShell>
  );
}
