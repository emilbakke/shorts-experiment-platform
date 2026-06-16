export function ExperimentProgressBar({ currentStep, totalSteps = 4 }: { currentStep: number; totalSteps?: number }) {
  const progress = Math.max(0, Math.min(100, (currentStep / totalSteps) * 100));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.24em] text-white/60">
        <span>Fremdrift</span>
        <span>
          Trin {currentStep} af {totalSteps}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-red-500 transition-all duration-500" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}
