"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentShell } from "./ExperimentShell";
import { LikertScaleButtons } from "./LikertScaleButtons";
import { patchStudySession, readStudySession, routeForStudyState, studyBasePath } from "@/lib/study-session";
import type { ExperimentSession } from "@/lib/types";

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function StudyPostSurveyScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [feministAttitude, setFeministAttitude] = useState("");
  const [feminismTakenTooFar, setFeminismTakenTooFar] = useState("");
  const [traditionalGenderAttitude, setTraditionalGenderAttitude] = useState("");
  const [harderToBeAMan, setHarderToBeAMan] = useState("");
  const [division, setDivision] = useState("");
  const [genderConflictExaggeration, setGenderConflictExaggeration] = useState("");
  const [onlineMisinformation, setOnlineMisinformation] = useState("");
  const [perceivedContentType, setPerceivedContentType] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const session = readStudySession();
    if (!session.session_id) {
      router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
      return;
    }
    fetch(`/api/session?${new URLSearchParams({ session_id: session.session_id }).toString()}`)
      .then((response) => response.json() as Promise<ExperimentSession>)
      .then((serverSession) => {
        if (!["reel_completed", "post_survey", "complete"].includes(serverSession.study_state ?? "")) {
          router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
          return;
        }
        if (serverSession.study_state === "complete") {
          patchStudySession({ state: "complete", completed_at: serverSession.post_survey_completed_at ?? new Date().toISOString() });
          router.replace(`${studyBasePath}/complete${suffix(searchParams)}`);
          return;
        }
        patchStudySession({ state: "post_survey" });
      })
      .catch(() => {
        router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
      });
  }, [router, searchParams]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const requiredAnswers = [
      feministAttitude,
      feminismTakenTooFar,
      traditionalGenderAttitude,
      harderToBeAMan,
      division,
      genderConflictExaggeration,
      onlineMisinformation,
      perceivedContentType,
    ];
    if (requiredAnswers.some((answer) => !answer)) {
      setError("Vælg venligst et svar til alle spørgsmål.");
      return;
    }
    const session = readStudySession();
    if (!session.session_id) {
      router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
      return;
    }
    const postSurveyPayload = {
      feminist_attitude: Number(feministAttitude),
      feminism_taken_too_far: Number(feminismTakenTooFar),
      traditional_gender_attitude: Number(traditionalGenderAttitude),
      harder_to_be_a_man_today: Number(harderToBeAMan),
      social_division: Number(division),
      gender_conflict_exaggeration: Number(genderConflictExaggeration),
      online_misinformation: Number(onlineMisinformation),
      perceived_content_type: perceivedContentType,
      submitted_at: new Date().toISOString(),
    };
    window.localStorage.setItem("exp-video-study-post", JSON.stringify(postSurveyPayload));
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "study_post_survey", session_id: session.session_id, ...postSurveyPayload }),
      });
      if (!response.ok) {
        throw new Error("Kunne ikke afslutte undersøgelsen.");
      }
      const serverSession = (await response.json()) as ExperimentSession;
      patchStudySession({ state: "complete", completed_at: serverSession.post_survey_completed_at ?? new Date().toISOString() });
      router.push(`${studyBasePath}/complete${suffix(searchParams)}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Kunne ikke afslutte undersøgelsen.");
    }
  }

  return (
    <ExperimentShell
      step={3}
      title="Afsluttende spørgsmål"
      description='Besvar nedenstående spørgsmål, hvor 1 er "helt uenig" og 7 er "helt enig".'
    >
      <form onSubmit={submit} className="space-y-8 rounded-[2rem] border border-white/10 bg-white/6 p-6 shadow-2xl shadow-black/20 backdrop-blur" data-testid="study-post-form">
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Feminisme er vigtig for at skabe et mere retfærdigt samfund.
          <LikertScaleButtons name="post-feminist-attitude" value={feministAttitude} onChange={setFeministAttitude} />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Feminisme har taget overhånd.
          <LikertScaleButtons
            name="post-feminism-taken-too-far"
            value={feminismTakenTooFar}
            onChange={setFeminismTakenTooFar}
          />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Traditionelle kønsroller er ofte bedst for samfundet.
          <LikertScaleButtons
            name="post-traditional-gender-attitude"
            value={traditionalGenderAttitude}
            onChange={setTraditionalGenderAttitude}
          />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Det er blevet sværere at være mand i dag end tidligere.
          <LikertScaleButtons
            name="post-harder-to-be-a-man"
            value={harderToBeAMan}
            onChange={setHarderToBeAMan}
          />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Samfundet bliver mere og mere splittet.
          <LikertScaleButtons name="post-division" value={division} onChange={setDivision} />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Offentlige diskussioner online overdriver ofte konflikter
          <LikertScaleButtons
            name="post-gender-conflict-exaggeration"
            value={genderConflictExaggeration}
            onChange={setGenderConflictExaggeration}
          />
        </label>
        <label className="block space-y-4 text-sm font-medium text-white/84">
          Jeg støder ofte på misinformation og falske udsagn online.
          <LikertScaleButtons
            name="post-online-misinformation"
            value={onlineMisinformation}
            onChange={setOnlineMisinformation}
          />
        </label>
        <fieldset className="space-y-4 text-sm font-medium text-white/84">
          <legend>Lagde du mærke til videoer om køn, mænds rettigheder, feminisme eller forhold mellem mænd og kvinder?</legend>
          <div className="grid gap-3">
            {[
              ["nej", "Nej"],
              ["en_eller_faa", "Ja, én eller få"],
              ["flere", "Ja, flere"],
              ["mange", "Ja, mange"],
              ["ved_ikke_husker_ikke", "Ved ikke / husker ikke"],
            ].map(([value, label]) => {
              const active = perceivedContentType === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setPerceivedContentType(value)}
                  className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                    active ? "border-red-500 bg-red-600/15 text-white" : "border-white/10 bg-zinc-950/45 text-white/84 hover:border-white/30"
                  }`}
                  aria-pressed={active}
                  data-testid={`post-content-type-${value}`}
                >
                  <span>{label}</span>
                  <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-[11px] ${active ? "border-red-400 bg-red-500 text-white" : "border-white/25 text-white/60"}`}>
                    {active ? "●" : ""}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        {error ? <p className="rounded-2xl bg-red-500/12 px-4 py-3 text-sm font-medium text-red-200">{error}</p> : null}

        <div className="flex flex-wrap gap-3">
          <button type="submit" data-testid="study-post-submit" className="inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500">
            Videre
          </button>
        </div>
      </form>
    </ExperimentShell>
  );
}
