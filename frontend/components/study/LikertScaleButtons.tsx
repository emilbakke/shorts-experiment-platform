"use client";

type LikertScaleButtonsProps = {
  value: string;
  onChange: (value: string) => void;
  name: string;
};

const likertPoints = ["1", "2", "3", "4", "5", "6", "7"] as const;

export function LikertScaleButtons({ value, onChange, name }: LikertScaleButtonsProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-7 items-center text-xs text-white/60">
        <span className="col-span-1 justify-self-center whitespace-nowrap">Helt uenig</span>
        <span className="col-span-5" />
        <span className="col-span-1 justify-self-center whitespace-nowrap">Helt enig</span>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {likertPoints.map((point) => {
          const active = value === point;
          return (
            <button
              key={`${name}-${point}`}
              type="button"
              onClick={() => onChange(point)}
              className={`flex h-11 w-11 justify-self-center items-center justify-center rounded-full border text-sm font-semibold transition ${
                active
                  ? "border-red-500 bg-red-600 text-white shadow-lg shadow-red-900/30"
                  : "border-white/15 bg-zinc-950/70 text-white/84 hover:border-white/35 hover:bg-zinc-900"
              }`}
              aria-pressed={active}
              data-testid={`${name}-${point}`}
            >
              {point}
            </button>
          );
        })}
      </div>
    </div>
  );
}
