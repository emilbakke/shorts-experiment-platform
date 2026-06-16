"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExperimentShell } from "./ExperimentShell";
import { conditionForAssignment, patchStudySession, readStudySession, routeForStudyState, studyBasePath } from "@/lib/study-session";
import type { Video } from "@/lib/types";

function suffix(searchParams: URLSearchParams) {
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export function StudyInstructionsScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const dogSoundRef = useRef<HTMLAudioElement>(null);
  const videoUnlockRef = useRef<HTMLVideoElement>(null);
  const startingReelRef = useRef(false);
  const [attentionPassed, setAttentionPassed] = useState(false);
  const [unlockVideoUrl, setUnlockVideoUrl] = useState<string | null>(null);
  const [attentionMessage, setAttentionMessage] = useState("");
  const [startingReel, setStartingReel] = useState(false);

  useEffect(() => {
    const session = readStudySession();
    if (!session.assignment || !session.session_id) {
      router.replace(`${studyBasePath}/pre${suffix(searchParams)}`);
      return;
    }
    if (!["instructions", "assigned"].includes(session.state)) {
      router.replace(`${routeForStudyState(session.state)}${suffix(searchParams)}`);
      return;
    }

    const condition = conditionForAssignment(session.assignment);
    const localSessionId = session.session_id;
    let cancelled = false;
    fetch(`/api/study/shorts?${new URLSearchParams({ condition, session_id: localSessionId }).toString()}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`))))
      .then((payload: Video[]) => {
        if (cancelled) return;
        setUnlockVideoUrl(payload[0]?.videoUrl ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setUnlockVideoUrl(null);
      });

    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  function playDogSound() {
    const audio = dogSoundRef.current;

    if (!audio) {
      return;
    }

    audio.currentTime = 0;
    void audio.play();
  }

  function answerAttentionCheck(answer: "hund" | "elefant" | "kat") {
    playDogSound();

    if (answer === "hund") {
      setAttentionPassed(true);
      setAttentionMessage("Korrekt. Du kan nu starte videofeedet.");
      window.localStorage.setItem(
        "exp-video-study-instructions-attention",
        JSON.stringify({ answer, passed: true, completed_at: new Date().toISOString() }),
      );
      return;
    }

    setAttentionPassed(false);
    setAttentionMessage("Det var ikke rigtigt. Skru op for lyden på din telefon og prøv igen.");
  }

  async function unlockInlineVideoPlayback() {
    const video = videoUnlockRef.current;
    if (!video) return;

    video.muted = false;
    video.volume = 1;
    video.playsInline = true;
    try {
      video.currentTime = 0;
    } catch {
      // Some mobile browsers disallow seeking before metadata is loaded.
    }

    try {
      const playback = video.play();
      if (playback) {
        await Promise.race([
          playback,
          new Promise((resolve) => window.setTimeout(resolve, 1200)),
        ]);
      }
    } catch {
      // iOS may still refuse if the media file is not ready; the reel route retries playback after route load.
    }
  }

  function startReelFromPress() {
    if (!attentionPassed || startingReelRef.current) return;
    void startReel();
  }

  async function startReel() {
    if (!attentionPassed) {
      setAttentionMessage("Lyt til lyden og vælg det dyr, du hører, før du starter videofeedet.");
      playDogSound();
      return;
    }
    if (startingReelRef.current) return;

    startingReelRef.current = true;
    setStartingReel(true);
    await unlockInlineVideoPlayback();
    patchStudySession({ state: "assigned" });
    router.replace(`${studyBasePath}/reel${suffix(searchParams)}`);
  }

  return (
    <ExperimentShell
      step={2}
      title="Sådan bruger du videofeedet"
      description="Næste del er et kort videofeed. Her er alt, du skal vide, før du starter."
    >
      {unlockVideoUrl ? (
        <video
          ref={videoUnlockRef}
          src={unlockVideoUrl}
          preload="auto"
          muted={false}
          playsInline
          aria-hidden="true"
          tabIndex={-1}
          className="pointer-events-none fixed bottom-0 left-0 h-px w-px opacity-0"
        />
      ) : null}
      <div className="space-y-5 rounded-[2rem] border border-white/10 bg-white/6 p-5 shadow-2xl shadow-black/20 backdrop-blur sm:p-6" data-testid="study-instructions">
        <div className="grid gap-5 sm:grid-cols-[0.9fr_1.1fr] sm:items-center">
          <div className="mx-auto w-full max-w-[220px] rounded-[2rem] border border-white/12 bg-black p-3 shadow-2xl shadow-black/30">
            <div className="relative aspect-[9/16] overflow-hidden rounded-[1.4rem] bg-zinc-900">
              <div className="absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-zinc-700 to-zinc-950" />
              <div className="absolute inset-x-6 top-10 h-24 rounded-full bg-white/8 blur-xl" />
              <div className="absolute left-1/2 top-8 flex -translate-x-1/2 flex-col items-center gap-2 text-white">
                <span className="text-2xl font-black leading-none text-white/85">↑</span>
                <div className="h-20 w-1 rounded-full bg-white/18">
                  <div className="mx-auto h-10 w-1 rounded-full bg-white/70" />
                </div>
                <span className="text-2xl font-black leading-none text-white/85">↓</span>
              </div>
              <div className="absolute inset-x-4 top-[58%] text-center text-white">
                <p className="text-sm font-black">Swipe op eller ned</p>
                <p className="mt-1 text-xs font-semibold text-white/62">Du kan altid gå videre</p>
              </div>
              <div className="absolute right-3 top-1/2 flex -translate-y-1/2 flex-col gap-4 opacity-60">
                <div className="h-8 w-8 rounded-full bg-white/18" />
                <div className="h-8 w-8 rounded-full bg-white/18" />
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/22 text-sm font-black text-white">↓</div>
              </div>
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black to-transparent p-4">
                <div className="h-3 w-24 rounded-full bg-white/80" />
                <div className="mt-2 h-2 w-32 rounded-full bg-white/35" />
              </div>
            </div>
          </div>

          <div className="space-y-4">
            {[
              {
                number: "1",
                title: "Se videoerne i feedet",
                text: "Videoerne starter automatisk. Bliv i feedet, indtil tiden er gået (4 minutter) for at gennemføre studiet. Skru op for lyden på din telefon, inden du starter.",
              },
              {
                number: "2",
                title: "Skift video",
                text: "Swipe op eller ned på telefonen når du vil se noget andet - det er ikke vigtigt du ser en video færdig. ",
                emphasis: "Hvis du ikke har lyst til at se en video, skal du bare scrolle videre til den næste.",
                textAfter: " Du kan også trykke på pil-knappen i højre side.",
              },
              {
                number: "3",
                title: "Svar bagefter",
                text: "Når tiden er gået, bliver du sendt videre til de afsluttende spørgsmål om videoerne og dine holdninger.",
              },
            ].map(({ number, title, text, emphasis, textAfter }) => (
              <div key={number} className="flex gap-4 rounded-[1.5rem] border border-white/10 bg-black/20 p-4">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-600 text-sm font-black text-white">{number}</span>
                <div>
                  <h2 className="text-base font-bold text-white">{title}</h2>
                  <p className="mt-1 text-sm leading-6 text-white/68">
                    {text}
                    {emphasis ? <strong className="font-black text-white/90">{emphasis}</strong> : null}
                    {textAfter}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          className="rounded-[1.75rem] border border-white/10 bg-black/24 p-4 sm:p-5"
          data-testid="study-attention-check"
        >
          <audio ref={dogSoundRef} src="/study/attention-dog.ogg" preload="auto" data-testid="study-attention-dog-audio" />
          <div className="grid gap-4 sm:grid-cols-[0.9fr_1.1fr] sm:items-center">
            <div className="overflow-hidden rounded-[1.5rem] border border-white/10 bg-sky-950/40">
              <Image
                src="/study/attention-elephant.jpg"
                width={960}
                height={1440}
                alt="Billede af en elefant"
                data-testid="study-attention-elephant"
                className="h-48 w-full object-cover object-[center_28%] sm:h-56"
                priority
              />
            </div>

            <div>
              <p className="text-xs font-black uppercase tracking-[0.2em] text-red-200">Lydtjek</p>
              <h2 className="mt-2 text-lg font-bold text-white">Hvilket dyr hører du?</h2>
              <p className="mt-1 text-sm leading-6 text-white/68">
                Der vises et billede, men du skal svare ud fra lyden. Tryk på lydknappen, skru op, og vælg det dyr du hører.
              </p>
              <button
                type="button"
                onClick={playDogSound}
                data-testid="study-attention-play-sound"
                className="mt-4 inline-flex h-10 items-center justify-center rounded-full bg-white px-4 text-sm font-bold text-zinc-950 transition hover:bg-zinc-200"
              >
                Afspil lyd
              </button>
              <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Svarmuligheder til lydtjek">
                {[
                  ["hund", "Hund"],
                  ["elefant", "Elefant"],
                  ["kat", "Kat"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => answerAttentionCheck(value as "hund" | "elefant" | "kat")}
                    data-testid={`study-attention-answer-${value}`}
                    className="inline-flex h-10 items-center justify-center rounded-full border border-white/14 px-4 text-sm font-semibold text-white transition hover:border-white/40 hover:bg-white/10"
                  >
                    {label}
                  </button>
                ))}
              </div>
              {attentionMessage ? (
                <p
                  className={`mt-3 text-sm font-semibold ${attentionPassed ? "text-emerald-200" : "text-amber-200"}`}
                  data-testid="study-attention-message"
                  aria-live="polite"
                >
                  {attentionMessage}
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onPointerDown={startReelFromPress}
            onTouchStart={startReelFromPress}
            onMouseDown={startReelFromPress}
            onClick={() => void startReel()}
            disabled={!attentionPassed || startingReel}
            data-testid="study-instructions-start"
            className="inline-flex h-12 items-center justify-center rounded-full bg-red-600 px-6 text-sm font-semibold text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-white/45"
          >
            {startingReel ? "Starter videofeedet…" : "Start videofeedet"}
          </button>
        </div>
      </div>
    </ExperimentShell>
  );
}
