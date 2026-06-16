function formatSeconds(remainingSeconds: number) {
  const safe = Math.max(0, remainingSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function ExperimentTimer({ remainingSeconds, totalSeconds }: { remainingSeconds: number; totalSeconds: number }) {
  const progress = totalSeconds > 0 ? Math.max(0, Math.min(100, ((totalSeconds - remainingSeconds) / totalSeconds) * 100)) : 0;

  return (
    <div className="rounded-lg border border-white/10 bg-black/45 px-2.5 py-1.5 text-white shadow-lg backdrop-blur" data-testid="study-timer">
      <div>
        <p className="text-[8px] font-semibold uppercase tracking-[0.14em] text-white/60">Tid tilbage</p>
        <p className="mt-0.5 text-base font-bold leading-none tabular-nums">{formatSeconds(remainingSeconds)}</p>
        <div className="mt-1 w-14">
          <div className="h-0.5 overflow-hidden rounded-full bg-white/12">
            <div className="h-full rounded-full bg-red-500 transition-all duration-1000" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}
