export default function Loading() {
  return (
    <main className="min-h-screen bg-white pt-14" aria-busy="true" data-testid="route-loading-state">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-6 md:px-6">
        <div className="flex items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm font-medium text-zinc-600">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-blue-500" />
          Opdaterer feed…
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {Array.from({ length: 10 }).map((_, index) => (
            <div key={`short-${index}`} className="aspect-[9/16] animate-pulse rounded-2xl bg-zinc-200" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={`card-${index}`} className="space-y-3">
              <div className="aspect-video animate-pulse rounded-xl bg-zinc-200" />
              <div className="space-y-2">
                <div className="h-4 animate-pulse rounded bg-zinc-200" />
                <div className="h-4 w-3/4 animate-pulse rounded bg-zinc-200" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
