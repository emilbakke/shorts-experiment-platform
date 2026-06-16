"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { EntrySurveyGate } from "@/components/EntrySurveyModal";
import { Header } from "@/components/Header";
import { SessionUrlSync } from "@/components/SessionUrlSync";
import { isStudyPath } from "@/lib/study-session";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isStudyRoute = pathname === "/" || isStudyPath(pathname);

  if (isStudyRoute) {
    return <main className="min-h-screen bg-zinc-950">{children}</main>;
  }

  return (
    <EntrySurveyGate>
      <SessionUrlSync>
        <Header />
        <main className="min-h-screen pt-14">{children}</main>
      </SessionUrlSync>
    </EntrySurveyGate>
  );
}
