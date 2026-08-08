import { useEffect, useState } from "react";
import { StoryCard } from "./components/StoryCard";
import type { Story } from "./types";

const LIMIT = 24;

export default function App() {
  const [stories, setStories] = useState<Story[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/stories?limit=${LIMIT}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStories)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen bg-white font-sans dark:bg-ink-900">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold text-ink-900 dark:text-white">
            Presswake
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-white/50">
            How every outlet covered the same story &mdash; who published, when,
            and who didn&rsquo;t.
          </p>
        </header>

        {error && (
          <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            Could not reach the API: {error}. Is <code>make api</code> running?
          </p>
        )}

        {stories && stories.length === 0 && (
          <p className="text-sm text-ink-500">
            No multi-outlet stories yet. Run <code>make recluster</code>.
          </p>
        )}

        {stories && stories.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stories.map((story) => (
              <StoryCard key={story.id} story={story} />
            ))}
          </div>
        )}

        {!stories && !error && (
          <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>
        )}
      </div>
    </div>
  );
}
