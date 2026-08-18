import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CategoryTabs } from "./CategoryTabs";
import { StoryCard } from "./StoryCard";
import { TeamSelect } from "./TeamSelect";
import type { CategoryTab, Story, TeamOption } from "../types";

/** Cards per fetch. Small first paint; "More" appends another page. */
const PAGE = 15;

export function Feed() {
  // Both undefined on "/", either set by its route segment. One component
  // serves every combination, so the controls never unmount between views.
  const { category, team } = useParams();
  const [stories, setStories] = useState<Story[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [tabs, setTabs] = useState<CategoryTab[]>([]);
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/categories")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setTabs)
      .catch(() => setTabs([]));
    fetch("/api/teams")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setTeams)
      .catch(() => setTeams([]));
  }, []);

  const fetchPage = useCallback(
    (offset: number): Promise<Story[]> => {
      const q =
        (category ? `&category=${encodeURIComponent(category)}` : "") +
        (team ? `&team=${encodeURIComponent(team)}` : "");
      return fetch(`/api/stories?limit=${PAGE}&offset=${offset}${q}`).then((r) =>
        r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)),
      );
    },
    [category, team],
  );

  useEffect(() => {
    setStories(null);
    setHasMore(false);
    fetchPage(0)
      .then((batch) => {
        setStories(batch);
        // A full page probably has more behind it. When the corpus size is
        // an exact multiple of PAGE, the reader gets one "More" click that
        // returns nothing and quietly retires the button -- cheaper than a
        // count query on every load.
        setHasMore(batch.length === PAGE);
      })
      .catch((e: Error) => setError(e.message));
  }, [fetchPage]);

  async function loadMore() {
    if (!stories) return;
    setLoadingMore(true);
    try {
      const batch = await fetchPage(stories.length);
      setStories([...stories, ...batch]);
      setHasMore(batch.length === PAGE);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  const withTabs = (inner: React.ReactNode) => (
    <>
      <TeamSelect teams={teams} />
      {/* Tabs link inside the selected team, so the two filters compose.
          Rooted at /stories since the brief took over "/". */}
      <CategoryTabs tabs={tabs} base={team ? `/stories/t/${team}` : "/stories"} />
      {inner}
    </>
  );

  if (error) {
    return withTabs(
      <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Could not reach the API: {error}. Is <code>make api</code> running?
      </p>
    );
  }

  if (!stories) {
    return withTabs(
      <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>,
    );
  }

  if (stories.length === 0) {
    return withTabs(
      <p className="text-sm text-ink-500 dark:text-white/50">
        {category || team
          ? "Nothing here yet."
          : "No multi-outlet stories yet. Run make recluster."}
      </p>,
    );
  }

  return withTabs(
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {stories.map((story) => (
          <StoryCard key={story.id} story={story} />
        ))}
      </div>
      {hasMore && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-full border border-ink-200 px-4 py-1.5 text-xs
                       text-ink-500 transition-colors hover:border-ink-500/40
                       hover:text-ink-900 disabled:opacity-50
                       dark:border-white/15 dark:text-white/60
                       dark:hover:text-white"
          >
            {loadingMore ? "Loading…" : "More stories"}
          </button>
        </div>
      )}
    </>,
  );
}
