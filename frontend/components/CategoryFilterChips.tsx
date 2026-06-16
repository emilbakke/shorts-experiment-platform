import Link from "next/link";
import type { Condition } from "@/lib/types";

function labelFor(topic: string): string {
  if (!topic) return "Alle";
  return topic
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toLocaleUpperCase() + part.slice(1))
    .join(" ");
}

function hrefFor(topic: string | null, condition: Condition, contentPool?: string | null, sessionId?: string | null): string {
  const params = new URLSearchParams({ condition });
  if (contentPool) params.set("content_pool", contentPool);
  if (sessionId) params.set("session_id", sessionId);
  if (topic) params.set("category", topic);
  const query = params.toString();
  return query ? `/platform?${query}` : "/platform";
}

export function CategoryFilterChips({
  topics,
  selected,
  condition,
  contentPool,
  sessionId,
}: {
  topics: string[];
  selected?: string | null;
  condition: Condition;
  contentPool?: string | null;
  sessionId?: string | null;
}) {
  const normalizedSelected = (selected || "").toLowerCase();
  const visibleTopics = topics.filter(Boolean).slice(0, 18);

  return (
    <nav className="mb-4 flex items-center gap-2 overflow-x-auto pb-1" aria-label="Emnefiltre" data-testid="category-filter-chips">
      <Link
        href={hrefFor(null, condition, contentPool, sessionId)}
        className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
          !normalizedSelected ? "bg-zinc-950 text-white" : "bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
        }`}
        aria-current={!normalizedSelected ? "page" : undefined}
      >
        Alle
      </Link>
      {visibleTopics.map((topic) => {
        const active = normalizedSelected === topic.toLowerCase();
        return (
          <Link
            key={topic}
            href={hrefFor(topic, condition, contentPool, sessionId)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              active ? "bg-zinc-950 text-white" : "bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
            }`}
            aria-current={active ? "page" : undefined}
          >
            {labelFor(topic)}
          </Link>
        );
      })}
    </nav>
  );
}
