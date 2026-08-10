import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import { useFavorites } from "../lib/favorites";
import { StoryCard } from "./StoryCard";
import type { Story } from "../types";

export function FavoritesPage() {
  const { session, loading: authLoading } = useAuth();
  // Re-fetch whenever the set changes, so unstarring a card here removes it
  // from the list rather than leaving a stale row behind.
  const { ids } = useFavorites();
  const [stories, setStories] = useState<Story[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    apiFetch("/api/favorites")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStories)
      .catch((e: Error) => setError(e.message));
  }, [session, ids]);

  // Wait for the session to resolve before deciding -- otherwise a signed-in
  // user sees "sign in to save stories" for a frame on every reload.
  if (authLoading) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  if (!session) {
    return (
      <div className="text-sm text-ink-500 dark:text-white/50">
        <p>
          <Link to="/login" className="underline">
            Sign in
          </Link>{" "}
          to save stories and find them here later.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
        Could not load favorites: {error}
      </p>
    );
  }

  if (!stories) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-ink-900 dark:text-white">
        Saved stories
      </h1>

      {stories.length === 0 ? (
        <p className="text-sm text-ink-500 dark:text-white/50">
          Nothing saved yet. Tap the star on any story to keep it here.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {stories.map((story) => (
            <StoryCard key={story.id} story={story} />
          ))}
        </div>
      )}
    </div>
  );
}
