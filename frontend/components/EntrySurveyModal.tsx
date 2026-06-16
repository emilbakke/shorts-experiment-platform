"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { activeCondition, persistSurveyAnswers, sessionId, surveyCompleted, userId } from "@/lib/analytics";
import type { EntrySurveyPayload } from "@/lib/types";

const householdOptions = [
  { value: "living_with_parents", label: "Ved forældre" },
  { value: "living_alone", label: "Alene" },
  { value: "living_with_partner_or_roommate", label: "Med sambo" },
] as const;

const regionOptions = [
  { value: "hovedstaden", label: "Region Hovedstaden" },
  { value: "sjælland", label: "Region Sjælland" },
  { value: "syddanmark", label: "Region Syddanmark" },
  { value: "midtjylland", label: "Region Midtjylland" },
  { value: "nordjylland", label: "Region Nordjylland" },
] as const;

const educationOptions = ["Grundskole", "Gymnasial", "Erhvervsuddannelse", "Kort videregående", "Bachelor", "Kandidat eller højere"];

export function EntrySurveyModal({ onComplete }: { onComplete: () => void }) {
  const searchParams = useSearchParams();
  const [gender, setGender] = useState("woman");
  const [age, setAge] = useState("24");
  const [household, setHousehold] = useState<EntrySurveyPayload["household_living_arrangement"]>("living_with_partner_or_roommate");
  const [education, setEducation] = useState("Bachelor");
  const [region, setRegion] = useState<EntrySurveyPayload["region_dk"]>("hovedstaden");
  const [orientation, setOrientation] = useState("5");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const numericAge = Number(age);
    const numericOrientation = Number(orientation);
    if (!Number.isFinite(numericAge) || numericAge < 13 || numericAge > 120) {
      setError("Angiv en gyldig alder mellem 13 og 120.");
      return;
    }
    if (!Number.isFinite(numericOrientation) || numericOrientation < 0 || numericOrientation > 10) {
      setError("Vælg en placering på skalaen fra 0 til 10.");
      return;
    }

    setSubmitting(true);
    const condition = activeCondition();
    const payload: EntrySurveyPayload = {
      session_id: sessionId(),
      user_id: userId(),
      condition,
      gender,
      age: numericAge,
      household_living_arrangement: household,
      education,
      region_dk: region,
      left_right_orientation: numericOrientation,
    };

    try {
      const response = await fetch("/api/session/survey", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.error === "string" ? body.error : "Kunne ikke gemme spørgeskemaet");
      }
      persistSurveyAnswers(payload);
      onComplete();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Kunne ikke gemme spørgeskemaet");
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    const condition = searchParams.get("condition");
    if (condition) window.localStorage.setItem("exp-video-condition", condition);
  }, [searchParams]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4 py-6" role="dialog" aria-modal="true" aria-labelledby="entry-survey-title" data-testid="entry-survey-modal">
      <form onSubmit={submit} className="max-h-full w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl md:p-8">
        <div className="mb-5 flex items-start gap-4">
          <span className="flex h-10 w-14 shrink-0 items-center justify-center rounded-xl bg-red-600 text-lg font-black text-white">▶</span>
          <div>
            <h1 id="entry-survey-title" className="text-2xl font-bold text-zinc-950">Før du begynder at se videoer</h1>
            <p className="mt-1 text-sm text-zinc-600">Besvar disse korte baggrundsspørgsmål én gang for denne session. Derefter kan du bruge søgning, anbefalinger, videosider og korte videoer.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-zinc-800">
            Køn
            <select value={gender} onChange={(event) => setGender(event.target.value)} className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-blue-500">
              <option value="woman">Kvinde</option>
              <option value="man">Mand</option>
              <option value="non_binary">Ikke-binær</option>
              <option value="prefer_not_to_say">Ønsker ikke at svare</option>
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-zinc-800">
            Alder
            <input value={age} onChange={(event) => setAge(event.target.value)} type="number" min="13" max="120" required className="h-11 w-full rounded-xl border border-zinc-300 px-3 text-sm outline-none focus:border-blue-500" />
          </label>

          <label className="space-y-2 text-sm font-medium text-zinc-800">
            Boligsituation
            <select value={household} onChange={(event) => setHousehold(event.target.value as EntrySurveyPayload["household_living_arrangement"])} className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-blue-500">
              {householdOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-zinc-800">
            Uddannelse
            <select value={education} onChange={(event) => setEducation(event.target.value)} className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-blue-500">
              {educationOptions.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-zinc-800 md:col-span-2">
            Region i Danmark
            <select value={region} onChange={(event) => setRegion(event.target.value as EntrySurveyPayload["region_dk"])} className="h-11 w-full rounded-xl border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-blue-500">
              {regionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>

          <label className="space-y-3 text-sm font-medium text-zinc-800 md:col-span-2">
            Politisk placering fra venstre mod højre
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-zinc-600">Venstre</span>
              <input value={orientation} onChange={(event) => setOrientation(event.target.value)} type="range" min="0" max="10" step="1" className="w-full accent-red-600" aria-label="Politisk placering fra venstre mod højre" />
              <span className="text-xs font-semibold text-zinc-600">Højre</span>
            </div>
            <div className="text-center text-sm text-zinc-700">Valgt: {orientation}</div>
          </label>
        </div>

        {error ? <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p> : null}

        <div className="mt-6 flex justify-end">
          <button type="submit" disabled={submitting} className="rounded-full bg-zinc-950 px-6 py-3 text-sm font-semibold text-white hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400" data-testid="entry-survey-submit">
            {submitting ? "Gemmer…" : "Start visning"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function EntrySurveyGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setReady(surveyCompleted());
    setChecked(true);
  }, []);

  if (!checked) {
    return <div className="min-h-screen bg-white" aria-hidden="true" />;
  }

  if (!ready) {
    return <EntrySurveyModal onComplete={() => setReady(true)} />;
  }

  return <>{children}</>;
}
