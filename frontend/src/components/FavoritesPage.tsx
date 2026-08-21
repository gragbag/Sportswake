import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import { useFavorites } from "../lib/favorites";
import { StoryRow } from "./StoryRow";
import { SlugRule } from "./press";
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
    return <p className="t-wire pt-8 text-ink-mute">Loading&hellip;</p>;
  }

  if (!session) {
    return (
      <div className="pt-8">
        <p className="t-read text-ink-mute">
          <Link
            to="/login"
            className="border-b border-spot pb-0.5 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
          >
            Sign in
          </Link>{" "}
          to save stories and find them here later.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-l-2 border-spot pt-8 pl-4">
        <p className="t-wire text-ink">The wire is down</p>
        <p className="t-read mt-1 text-ink-mute">Could not load favorites: {error}</p>
      </div>
    );
  }

  if (!stories) {
    return <p className="t-wire pt-8 text-ink-mute">Loading&hellip;</p>;
  }

  return (
    <div>
      <div className="pt-8">
        <SlugRule
          label="Saved"
          count={stories.length > 0 ? stories.length : undefined}
        />
      </div>

      {stories.length === 0 ? (
        <p className="t-read pt-6 text-ink-mute">
          Nothing saved yet. Tap the star on any story to keep it here.
        </p>
      ) : (
        <ul className="pt-6">
          {stories.map((story) => (
            <StoryRow key={story.id} story={story} />
          ))}
        </ul>
      )}
    </div>
  );
}
