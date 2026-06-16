import type { Condition } from "@/lib/types";

export function ExperimentBanner({ condition }: { condition: Condition }) {
  return (
    <section className="mb-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4" data-testid="experiment-banner" data-condition={condition} aria-label="Visningssession">
      <h1 className="text-xl font-bold text-zinc-950">Anbefalet til dig</h1>
      <p className="mt-1 text-sm text-zinc-600">Udforsk videoer, søg efter et emne, eller fortsæt med at se fra feedet.</p>
    </section>
  );
}
