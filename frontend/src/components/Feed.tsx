import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CategoryTabs } from "./CategoryTabs";
import { StoryCard } from "./StoryCard";
import type { CategoryTab, Story } from "../types";

const LIMIT = 24;

export function Feed() {
  // Undefined on "/", a slug on "/c/:category". One component serves both,
  // so the tab bar never unmounts and remounts between tabs.
  const { category } = useParams();
  const [stories, setStories] = useState<Story[] | null>(null);
  const [tabs, setTabs] = useState<CategoryTab[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/categories")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setTabs)
      .catch(() => setTabs([]));
  }, []);

  useEffect(() => {
    setStories(null);
    const q = category ? `&category=${encodeURIComponent(category)}` : "";
    fetch(`/api/stories?limit=${LIMIT}${q}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStories)
      .catch((e: Error) => setError(e.message));
  }, [category]);

  const withTabs = (inner: React.ReactNode) => (
    <>
      <CategoryTabs tabs={tabs} />
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
        {category
          ? "Nothing in this category yet."
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
