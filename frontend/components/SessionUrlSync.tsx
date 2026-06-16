"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { sessionId } from "@/lib/analytics";

export function SessionUrlSync({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const current = searchParams.get("session_id");
    const id = sessionId();
    if (current === id) {
      setReady(true);
      return;
    }
    setReady(false);
    const next = new URLSearchParams(searchParams.toString());
    next.set("session_id", id);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }, [pathname, router, searchParams]);

  if (!ready) {
    return <div className="min-h-screen bg-white" aria-hidden="true" />;
  }

  return <>{children}</>;
}
