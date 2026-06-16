"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { conditionLabel, normalizeCondition, testerConditions } from "@/lib/experiment";
import type { Condition } from "@/lib/types";

export function ConditionSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const parsedCondition = normalizeCondition(searchParams.get("condition"));
  const condition = parsedCondition === "treatment_problematic_content" ? parsedCondition : "control_recommendation";
  const [selectedCondition, setSelectedCondition] = useState<Condition>(condition);
  const [isPending, startTransition] = useTransition();

  const safeHref = useMemo(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("condition", "control_recommendation");
    next.set("content_pool", "safe");
    return `${pathname}?${next.toString()}`;
  }, [pathname, searchParams]);

  const problematicHref = useMemo(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("condition", "treatment_problematic_content");
    next.set("content_pool", "mixed");
    return `${pathname}?${next.toString()}`;
  }, [pathname, searchParams]);

  useEffect(() => {
    setSelectedCondition(condition);
  }, [condition]);

  useEffect(() => {
    router.prefetch(safeHref);
    router.prefetch(problematicHref);
  }, [problematicHref, router, safeHref]);

  function handleChange(nextCondition: Condition) {
    setSelectedCondition(nextCondition);
    const next = new URLSearchParams(searchParams.toString());
    next.set("condition", nextCondition);
    next.set("content_pool", nextCondition === "treatment_problematic_content" ? "mixed" : "safe");
    if (!next.get("session_id")) {
      const session = window.localStorage.getItem("exp-video-session");
      if (session) next.set("session_id", session);
    }
    window.localStorage.setItem("exp-video-condition", nextCondition);
    startTransition(() => {
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
      router.refresh();
    });
  }

  return (
    <label className="flex items-center gap-2 text-xs text-zinc-600" aria-label="Valg af indholdstilstand">
      <span className="hidden whitespace-nowrap md:inline">Indholdstilstand</span>
      <select
        value={selectedCondition}
        onChange={(event) => handleChange(event.target.value as Condition)}
        disabled={isPending}
        className="h-9 rounded-full border border-zinc-300 bg-white px-3 text-xs font-medium text-zinc-800 outline-none hover:border-zinc-400 focus:border-blue-500 disabled:cursor-wait disabled:opacity-80"
        data-testid="condition-selector"
      >
        {testerConditions.map((option) => (
          <option key={option} value={option}>
            {conditionLabel(option)}
          </option>
        ))}
      </select>
      {isPending ? (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-zinc-500" data-testid="condition-selector-pending">
          <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          Opdaterer…
        </span>
      ) : null}
    </label>
  );
}
