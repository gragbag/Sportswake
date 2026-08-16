import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CategoryTabs } from "./CategoryTabs";
import { StoryCard } from "./StoryCard";
import { TeamSelect } from "./TeamSelect";
import type { CategoryTab, Story, TeamOption } from "../types";

const LIMIT = 24;

export function Feed() {
  // Both undefined on "/", either set by its route segment. One component
  // serves every combination, so the controls never unmount between views.
  const { category, team } = useParams();
  const [stories, setStories] = useState<Story[] | null>(null);
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

  useEffect(() => {
    setStories(null);
    const q =
      (category ? `&category=${encodeURIComponent(category)}` : "") +
      (team ? `&team=${encodeURIComponent(team)}` : "");
    fetch(`/api/stories?limit=${LIMIT}${q}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStories)
      .catch((e: Error) => setError(e.message));
  }, [category, team]);

  const withTabs = (inner: React.ReactNode) => (
    <>
      <TeamSelect teams={teams} />
      {/* Tabs link inside the selected team, so the two filters compose. */}
      <CategoryTabs tabs={tabs} base={team ? `/t/${team}` : ""} />
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
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {stories.map((story) => (
        <StoryCard key={story.id} story={story} />
      ))}
    </div>,
  );
}
