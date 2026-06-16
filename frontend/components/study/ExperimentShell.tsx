import type { ReactNode } from "react";
import { ExperimentProgressBar } from "./ExperimentProgressBar";

export function ExperimentShell({
  step,
  title,
  description,
  children,
}: {
  step: number;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(239,68,68,0.18),_transparent_28%),linear-gradient(180deg,_#111827_0%,_#09090b_45%,_#050505_100%)] text-white">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-3xl">
          <div className="mb-6 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-red-600 text-xl font-black text-white shadow-lg shadow-red-600/30">▶</span>
          </div>
          <ExperimentProgressBar currentStep={step} />
        </div>

        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center py-8">
          <div className="mb-8">
            <h1 className="text-4xl font-black tracking-tight text-white sm:text-5xl">{title}</h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-white/72 sm:text-lg">{description}</p>
          </div>
          {children}
        </div>
      </div>
    </section>
  );
}
