import { SearchResultsList } from "@/components/SearchResultsList";
import { searchVideos } from "@/lib/data";
import { normalizeCondition } from "@/lib/experiment";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string; condition?: string; content_pool?: string }> }) {
  const params = await searchParams;
  const query = params.q ?? "";
  const condition = normalizeCondition(params.condition);
  const results = await searchVideos(query, condition, params.content_pool);
  return (
    <div className="px-4 py-6 md:px-6" data-testid="search-condition" data-condition={condition}>
      <SearchResultsList videos={results} query={query} condition={condition} contentPool={params.content_pool} />
    </div>
  );
}
