"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { isCondition } from "@/lib/experiment";

export function Header() {
  const searchParams = useSearchParams();
  const condition = searchParams.get("condition");
  const contentPool = searchParams.get("content_pool");
  const session = searchParams.get("session_id");
  const shouldCarryCondition = isCondition(condition);

  return (
    <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-4">
      <Link href="/platform" className="flex items-center gap-3 font-semibold text-zinc-950" aria-label="ViewTube forside">
        <span className="flex h-7 w-10 items-center justify-center rounded-lg bg-red-600 text-sm font-black text-white">▶</span>
        <span className="text-xl tracking-tight">ViewTube</span>
      </Link>
      <form action="/search" className="mx-auto flex w-full max-w-2xl items-center">
        {shouldCarryCondition ? <input type="hidden" name="condition" value={condition} /> : null}
        {contentPool ? <input type="hidden" name="content_pool" value={contentPool} /> : null}
        {session ? <input type="hidden" name="session_id" value={session} /> : null}
        <input
          name="q"
          type="search"
          placeholder="Søg"
          className="h-10 flex-1 rounded-l-full border border-zinc-300 px-5 text-sm outline-none focus:border-blue-500"
        />
        <button className="h-10 rounded-r-full border border-l-0 border-zinc-300 bg-zinc-50 px-6 text-sm font-medium hover:bg-zinc-100" type="submit">
          Søg
        </button>
      </form>
      <div className="flex items-center gap-3 text-sm text-zinc-700" aria-label="actions">
        <span className="sr-only" data-testid="internal-condition" data-condition={shouldCarryCondition ? condition : "control_recommendation"}>
          Internal condition hook
        </span>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 font-bold text-white">A</span>
      </div>
    </header>
  );
}
