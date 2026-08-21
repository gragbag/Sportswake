import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CategoryTabs } from "./CategoryTabs";
import { StoryRow } from "./StoryRow";
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
      <div className="border-l-2 border-spot pl-4">
        <p className="t-wire text-ink">The wire is down</p>
        <p className="t-read mt-1 max-w-[52ch] text-ink-mute">
          Could not reach the API: {error}. Is <code>make api</code> running?
        </p>
      </div>
    );
  }

  if (!stories) {
    return withTabs(
      <p className="t-wire text-ink-mute">Loading&hellip;</p>,
    );
  }

  if (stories.length === 0) {
    return withTabs(
      <p className="t-read text-ink-mute">
        {category || team
          ? "Nothing here yet."
          : "No multi-outlet stories yet. Run make recluster."}
      </p>,
    );
  }

  return withTabs(
    <>
      <ul>
        {stories.map((story) => (
          <StoryRow key={story.id} story={story} />
        ))}
      </ul>
      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          className="t-wire flex w-full cursor-pointer items-baseline gap-4 border-t border-rule pt-4 text-ink-mute hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot disabled:opacity-50"
        >
          {loadingMore ? "Loading…" : "More stories"}
          <span aria-hidden="true" className="h-px flex-1 bg-rule" />
          <span aria-hidden="true">↓</span>
        </button>
      )}
    </>,
  );
}
