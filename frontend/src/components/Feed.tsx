import { useEffect, useState } from "react";
import { StoryCard } from "./StoryCard";
import type { Story } from "../types";

const LIMIT = 24;

export function Feed() {
  const [stories, setStories] = useState<Story[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/stories?limit=${LIMIT}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStories)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Could not reach the API: {error}. Is <code>make api</code> running?
      </p>
    );
  }

  if (!stories) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  if (stories.length === 0) {
    return (
      <p className="text-sm text-ink-500">
        No multi-outlet stories yet. Run <code>make recluster</code>.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {stories.map((story) => (
        <StoryCard key={story.id} story={story} />
      ))}
    </div>
  );
}
