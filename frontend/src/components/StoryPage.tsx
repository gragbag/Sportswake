import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FavoriteButton } from "./FavoriteButton";
import type { StoryArticle, StoryDetail } from "../types";

/** "+0h", "+3h", "+2d" -- time since the first outlet published. */
function offsetFrom(firstIso: string, iso: string): string {
  const hours = (new Date(iso).getTime() - new Date(firstIso).getTime()) / 3600000;
  if (hours < 1) return `+${Math.round(hours * 60)}m`;
  if (hours < 48) return `+${Math.round(hours)}h`;
  return `+${Math.round(hours / 24)}d`;
}

type OutletGroup = { outlet: string; articles: StoryArticle[] };

/**
 * Group articles by outlet, outlets ordered by who published first.
 *
 * The API returns articles chronologically, so a Map preserves exactly that
 * ordering for free -- the first time an outlet appears is its first
 * publication. No sorting needed, and none should be added: "who broke it"
 * is the ordering the product is about.
 */
function groupByOutlet(articles: StoryArticle[]): OutletGroup[] {
  const byOutlet = new Map<string, StoryArticle[]>();
  for (const article of articles) {
    const existing = byOutlet.get(article.outlet);
    if (existing) existing.push(article);
    else byOutlet.set(article.outlet, [article]);
  }
  return [...byOutlet].map(([outlet, group]) => ({ outlet, articles: group }));
}

function Chevron() {
  return (
    <svg
      viewBox="0 0 12 12"
      className="h-2.5 w-2.5 shrink-0 transition-transform group-open:rotate-90"
      aria-hidden="true"
    >
      <path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function StoryPage() {
  const { storyId } = useParams();
  const [story, setStory] = useState<StoryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Reset on id change so story -> story navigation shows the loading
    // state rather than the previous story's content.
    setStory(null);
    setError(null);

    fetch(`/api/stories/${storyId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStory)
      .catch((e: Error) => setError(e.message));
  }, [storyId]);

  if (error) {
    return (
      <div className="text-sm">
        <p className="text-ink-500 dark:text-white/50">Story not found ({error}).</p>
        <Link to="/" className="mt-2 inline-block underline">
          Back to all stories
        </Link>
      </div>
    );
  }

  if (!story) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  const headline = story.summary_title ?? story.title;
  const groups = groupByOutlet(story.articles);

  return (
    <div>
      <Link
        to="/"
        className="text-xs text-ink-500 hover:text-ink-900 dark:text-white/50
                   dark:hover:text-white"
      >
        &larr; All stories
      </Link>

      {/* Two gap classes, and the responsive one wins where it applies:
          lg:gap-24 overrides gap-8 above 1024px no matter which order they
          sit in the string. gap-8 is the stacked-mobile gutter, lg:gap-24
          the desktop one between summary and coverage.
          minmax(0,1fr) rather than 1fr: without it a long unbroken headline
          can force the column past its share and push the sidebar
          off-screen. */}
      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-24">
        <article>
          <p className="text-xs tabular-nums text-ink-500 dark:text-white/50">
            {story.outlet_count} outlets &middot; {story.article_count} articles
            &middot; {story.span_hours}h span &middot; {groups[0]?.outlet} first
          </p>

          <div className="mt-2 flex items-start gap-3">
            <h1 className="text-2xl font-semibold leading-tight text-ink-900 dark:text-white">
              {headline}
            </h1>
            <div className="pt-1.5">
              <FavoriteButton storyId={story.id} />
            </div>
          </div>

          {story.summary_subhead && (
            <p className="mt-2 text-[15px] leading-snug text-ink-500 dark:text-white/60">
              {story.summary_subhead}
            </p>
          )}

          {/* Generated text is always labelled, with its sources beside it. */}
          {story.summary_bullets && story.summary_bullets.length > 0 && (
            <section className="mt-6 rounded-lg border border-ink-200 p-4 dark:border-white/10">
              <h2 className="text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:text-white/40">
                Overview &middot; AI-generated from the coverage
              </h2>
              <ul className="mt-3 space-y-2">
                {story.summary_bullets.map((bullet, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-sm leading-snug text-ink-900 dark:text-white/90"
                  >
                    <span className="text-ink-500 dark:text-white/30">&bull;</span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>

              {story.summary_people && story.summary_people.length > 0 && (
                <div className="mt-4 flex flex-wrap items-center gap-1">
                  <span className="mr-1 text-[11px] text-ink-500 dark:text-white/40">
                    People
                  </span>
                  {story.summary_people.map((person) => (
                    <span
                      key={person}
                      className="rounded bg-ink-50 px-1.5 py-0.5 text-[11px] text-ink-500
                                 dark:bg-white/10 dark:text-white/60"
                    >
                      {person}
                    </span>
                  ))}
                </div>
              )}
            </section>
          )}

          {story.summarized_at && (
            <p className="mt-6 text-[11px] text-ink-500 dark:text-white/30">
              Overview generated by {story.summary_model} on{" "}
              {new Date(story.summarized_at).toLocaleString()} from the{" "}
              {story.outlet_count} outlets listed. Not written or checked by a
              human.
            </p>
          )}
        </article>

        {/* Coverage: one row per outlet, ordered by who published first.
            Collapsed by default -- CBS filed 21 items on one story, so a flat
            list buries the fact that 32 outlets covered it at all. */}
        <aside
          className="h-fit rounded-lg border border-ink-200 lg:sticky lg:top-8
                     dark:border-white/10"
        >
          <h2 className="border-b border-ink-200 px-4 py-3 text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:border-white/10 dark:text-white/40">
            Coverage &middot; {story.outlet_count} outlets
          </h2>

          <ul className="max-h-[70vh] overflow-y-auto">
            {groups.map((group) => (
              <li
                key={group.outlet}
                className="border-b border-ink-200 last:border-0 dark:border-white/10"
              >
                {/* <details> gives keyboard and screen-reader support for
                    free; marker:hidden drops the native disclosure triangle
                    in favour of the chevron. */}
                <details className="group">
                  <summary
                    className="flex cursor-pointer list-none items-center gap-2 px-4 py-2
                               text-ink-500 hover:bg-ink-50
                               [&::-webkit-details-marker]:hidden
                               dark:text-white/60 dark:hover:bg-white/5"
                  >
                    <Chevron />
                    <span className="min-w-0 truncate text-[13px] text-ink-900 dark:text-white/90">
                      {group.outlet}
                    </span>
                    <span className="ml-auto shrink-0 text-[11px] tabular-nums">
                      {group.articles.length}
                    </span>
                    <span className="w-9 shrink-0 text-right text-[11px] tabular-nums">
                      {offsetFrom(story.first_at, group.articles[0].published_at)}
                    </span>
                  </summary>

                  <ol className="space-y-2 px-4 pb-3 pl-8">
                    {group.articles.map((article, i) => (
                      <li key={`${article.url}-${i}`} className="flex gap-2">
                        <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-ink-500 dark:text-white/30">
                          {offsetFrom(story.first_at, article.published_at)}
                        </span>
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noreferrer"
                          className="min-w-0 text-[12px] leading-snug text-ink-900 hover:underline dark:text-white/80"
                        >
                          {article.headline}
                        </a>
                      </li>
                    ))}
                  </ol>
                </details>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
