"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentShell } from "./ExperimentShell";
import { assignStudyCondition, conditionForAssignment, patchStudySession, readStudySession, routeForStudyState, studyBasePath } from "@/lib/study-session";
import { userId } from "@/lib/analytics";
import { norstatRedirectUrl, norstatUserId } from "@/lib/norstat";
import { recordStudyParticipation } from "@/lib/study-participation";

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function requestedDuration(searchParams: URLSearchParams) {
  const requested = Number(searchParams.get("duration_seconds") ?? "240");
  return Number.isFinite(requested) && requested > 0 ? Math.floor(requested) : 240;
}

export function StudyPreSurveyScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [ageGroup, setAgeGroup] = useState("");
  const [gender, setGender] = useState("");
  const [videoPlatformUse, setVideoPlatformUse] = useState("");
  const [politicalOrientation, setPoliticalOrientation] = useState("5");
  const [educationLevel, setEducationLevel] = useState("");
  const [cohabitationStatus, setCohabitationStatus] = useState("");
  const [employmentStatus, setEmploymentStatus] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const durationSeconds = useMemo(() => requestedDuration(searchParams), [searchParams]);

  useEffect(() => {
    const session = readStudySession();
    if (session.state === "entry") {
      router.replace(`${studyBasePath}${suffix(searchParams)}`);
      return;
    }
    if (!["pre_survey", "assigned"].includes(session.state)) {
      router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
    }
  }, [router, searchParams]);

  async function updateAgeGroup(value: string) {
    setAgeGroup(value);
    if (value !== "65+") return;
    const session = readStudySession();
    try { await recordStudyParticipation("accepted", "age_65_plus"); } catch { /* keep participant exit available */ }
    window.location.assign(norstatRedirectUrl("Screened", session.norstat_pid ?? searchParams.get("pid")));
  }

  function updateVideoPlatformUse(value: string) {
    setVideoPlatformUse(value);
    if (value === "never") {
      setSelectedPlatforms([]);
    }
  }

  function togglePlatform(value: string) {
    setSelectedPlatforms((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  async function submitSurvey() {
    if (submitting) return;
    setError(null);
    if (!ageGroup || !gender || !educationLevel || !cohabitationStatus || !employmentStatus || !videoPlatformUse) {
      setError("Vælg venligst et svar i alle felter.");
      return;
    }
    if (videoPlatformUse !== "never" && selectedPlatforms.length === 0) {
      setError("Vælg venligst mindst én videoplatform, eller vælg Aldrig ovenfor.");
      return;
    }
    setSubmitting(true);
    const localSession = readStudySession();
    const existingAssignment = localSession.assignment;
    const existingSessionId = localSession.session_id;
    const assignment = existingAssignment ?? assignStudyCondition();
    const condition = conditionForAssignment(assignment);
    const participantUserId = localSession.norstat_pid ? norstatUserId(localSession.norstat_pid, "") : userId();

    try {
      let sessionId = existingSessionId ?? localSession.study_id;
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "study_prepare",
          session_id: sessionId,
          condition,
          user_id: participantUserId,
          reel_duration_seconds: durationSeconds,
        }),
      });
      if (!response.ok) {
        throw new Error("Kunne ikke starte videosessionen.");
      }
      const payload = (await response.json()) as { session_id?: string };
      sessionId = payload.session_id ?? sessionId;

      const preSurveyPayload = {
        consent: true,
        research_use_consent: true,
        age_group: ageGroup,
        gender,
        video_platform_use: videoPlatformUse,
        political_orientation: Number(politicalOrientation),
        education_level: educationLevel,
        typical_video_platforms: selectedPlatforms,
        cohabitation_status: cohabitationStatus,
        employment_status: employmentStatus,
        norstat_pid: localSession.norstat_pid,
        submitted_at: new Date().toISOString(),
      };
      const surveyResponse = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action: "study_pre_survey",
          session_id: sessionId,
          user_id: participantUserId,
          condition,
          ...preSurveyPayload,
        }),
      });
      if (!surveyResponse.ok) {
        throw new Error("Kunne ikke gemme spørgeskemaet.");
      }

      patchStudySession({
        state: "instructions",
        assignment,
        session_id: sessionId,
        started_at: localSession.started_at ?? new Date().toISOString(),
      });
      window.localStorage.setItem("exp-video-study-pre", JSON.stringify(preSurveyPayload));
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set("duration_seconds", String(durationSeconds));
      window.location.assign(`${studyBasePath}/instructions?${nextParams.toString()}`);
    } catch (submitError) {
      setSubmitting(false);
      setError(submitError instanceof Error ? submitError.message : "Kunne ikke starte videosessionen.");
    }
  }

  return (
    <ExperimentShell
      step={1}
      title="Før videosessionen"
      description="Besvar de korte baggrundsspørgsmål, før videoerne begynder."
    >
      <div className="space-y-6 rounded-[2rem] border border-white/10 bg-white/6 p-6 shadow-2xl shadow-black/20 backdrop-blur" data-testid="study-pre-form">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-white/84">
            Aldersgruppe
            <select value={ageGroup} onChange={(event) => void updateAgeGroup(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none">
              <option value="" disabled>Vælg her...</option>
              {["18-20", "21-24", "25-29", "30-34", "35-44", "45-54", "55-64", "65+"].map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium text-white/84">
            Køn
            <select value={gender} onChange={(event) => setGender(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none">
              <option value="" disabled>Vælg her...</option>
              {[
                ["woman", "Kvinde"],
                ["man", "Mand"],
                ["non_binary", "Ikke-binær"],
                ["prefer_not_to_say", "Ønsker ikke at svare"],
              ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium text-white/84">
            Højeste gennemførte uddannelse
            <select value={educationLevel} onChange={(event) => setEducationLevel(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none">
              <option value="" disabled>Vælg her...</option>
              {[
                ["folkeskole", "Grundskole / folkeskole"],
                ["gymnasium", "Gymnasial uddannelse"],
                ["erhvervsuddannelse", "Erhvervsuddannelse"],
                ["kort_videregaende", "Kort videregående uddannelse"],
                ["mellem_videregaende", "Mellemlang videregående uddannelse"],
                ["lang_videregaende", "Lang videregående uddannelse"],
                ["phd", "Ph.d. eller tilsvarende"],
              ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium text-white/84">
            Boligsituation
            <select value={cohabitationStatus} onChange={(event) => setCohabitationStatus(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none">
              <option value="" disabled>Vælg her...</option>
              {[
                ["alene", "Bor alene"],
                ["samlevere", "Bor sammen med en eller flere"],
                ["foraeldre", "Bor hos forældre"],
              ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="space-y-2 text-sm font-medium text-white/84 sm:col-span-2">
            Hvad beskriver bedst din nuværende beskæftigelse?
            <select value={employmentStatus} onChange={(event) => setEmploymentStatus(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none">
              <option value="" disabled>Vælg her...</option>
              {[
                ["studerende", "Studerende"],
                ["fuldtid", "Fuldtidsarbejde"],
                ["deltid", "Deltidsarbejde"],
                ["selvstaendig", "Selvstændig"],
                ["arbejdssoegende", "Arbejdssøgende"],
                ["andet", "Andet"],
              ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="space-y-3 text-sm font-medium text-white/84 sm:col-span-2">
            Hvor vil du placere dig politisk fra venstre til højre?
            <input value={politicalOrientation} onChange={(event) => setPoliticalOrientation(event.target.value)} type="range" min="0" max="10" step="1" className="w-full accent-red-500" />
            <div className="flex justify-between text-xs text-white/60"><span>Venstre</span><span>Valgt: {politicalOrientation}</span><span>Højre</span></div>
          </label>
          <label className="space-y-2 text-sm font-medium text-white/84 sm:col-span-2">
            Hvor ofte anvender du videoplatforme?
            <select value={videoPlatformUse} onChange={(event) => updateVideoPlatformUse(event.target.value)} className="h-12 w-full rounded-2xl border border-white/10 bg-zinc-950/70 px-4 text-white outline-none" data-testid="study-video-platform-use">
              <option value="" disabled>Vælg her...</option>
              {[
                ["daily", "Dagligt"],
                ["weekly", "Flere gange om ugen"],
                ["monthly", "Et par gange om måneden"],
                ["rarely", "Sjældent"],
                ["never", "Aldrig"],
              ].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {videoPlatformUse !== "never" ? (
            <fieldset className="space-y-3 text-sm font-medium text-white/84 sm:col-span-2">
              <legend>Hvilke videoplatforme anvender du typisk?</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["youtube", "YouTube"],
                  ["tiktok", "TikTok"],
                  ["instagram", "Instagram"],
                  ["snapchat", "Snapchat"],
                  ["drtv", "DR TV"],
                  ["tv2play", "TV 2 Play"],
                  ["twitch", "Twitch"],
                  ["reddit", "Reddit"],
                  ["kick", "Kick"],
                  ["onlyfans", "OnlyFans"],
                  ["pornhub", "Pornhub"],
                  ["andet", "Andre platforme"],
                ].map(([value, label]) => {
                  const active = selectedPlatforms.includes(value);
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => togglePlatform(value)}
                      className={`flex items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                        active ? "border-red-500 bg-red-600/15 text-white" : "border-white/10 bg-zinc-950/45 text-white/84 hover:border-white/30"
                      }`}
                      aria-pressed={active}
                    >
                      <span>{label}</span>
                      <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-[11px] ${active ? "border-red-400 bg-red-500 text-white" : "border-white/25 text-white/60"}`}>
                        {active ? "✓" : ""}
                      </span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          ) : null}
        </div>

        {error ? <p className="rounded-2xl bg-red-500/12 px-4 py-3 text-sm font-medium text-red-200">{error}</p> : null}

        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={() => void submitSurvey()} disabled={submitting} data-testid="study-pre-submit" className="inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60">
            {submitting ? "Starter videoer…" : "Fortsæt til videoer"}
          </button>
        </div>
      </div>
    </ExperimentShell>
  );
}
