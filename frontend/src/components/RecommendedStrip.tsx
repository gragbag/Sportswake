import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/auth";
import { UNDERLINE } from "./press";
import { timeAgo } from "../lib/time";
import type { Story } from "../types";

/**
 * One shelf item.
 *
 * Not StoryRow: that component is a full-width row built to sit in a
 * vertical list, with a numeral column beside the headline and a sparkline
 * that has nowhere to go at 18rem wide. A shelf card stacks the same
 * information instead of laying it out beside itself, and drops the
 * sparkline and article count -- detail a reader glances past on a card
 * they have not yet decided to open.
 */
function RecommendedCard({ story }: { story: Story }) {
  const headline = story.summary_title ?? story.title;
  const slug = [
    ...story.teams.map((t) => t.code),
    ...story.categories.map((c) => c.label),
  ].join(" · ");

  return (
    <Link
      to={`/story/${story.id}`}
      className="flex h-full flex-col border-t border-rule pt-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-spot"
    >
      <span className="t-wire text-ink-mute">
        {story.outlet_count} outlet{story.outlet_count === 1 ? "" : "s"}
        {slug && (
          <>
            <span aria-hidden="true"> · </span>
            {slug}
          </>
        )}
      </span>

      <h3 className={`t-display mt-2 text-[1.0625rem] leading-[1.2] text-ink ${UNDERLINE}`}>
        {headline}
      </h3>

      {/* Pinned to the card's bottom via mt-auto, so the "first" line lands
          on the same baseline across a row of headlines with different
          lengths -- without it a two-line headline pushes its neighbour's
          meta line out of alignment. */}
      <p className="t-wire mt-auto pt-3 text-ink-mute">
        {story.outlets[0] && (
          <>
            <span className="text-ink">{story.outlets[0]}</span> first
            <span aria-hidden="true"> · </span>
          </>
        )}
        {timeAgo(story.last_at)}
      </p>
    </Link>
  );
}

/**
 * A horizontal shelf below the brief -- stories worth a look that the
 * reader has not already met today.
 *
 * Outside the brief's own key={slot}-remounting wrapper on purpose: this
 * has nothing to do with which edition is on screen, and remounting it on
 * every edition switch would refetch for no reason.
 *
 * Renders nothing while loading and nothing if the shelf comes back empty
 * -- an empty "Recommended" heading under the brief reads as broken, and a
 * loading skeleton for a below-the-fold module nobody has scrolled to yet
 * is effort spent on a flash no one sees.
 */
export function RecommendedStrip() {
  const [stories, setStories] = useState<Story[] | null>(null);

  useEffect(() => {
    apiFetch("/api/recommendations")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setStories)
      .catch(() => setStories([]));
  }, []);

  if (!stories || stories.length === 0) return null;

  return (
    <section className="border-t border-rule pt-8">
      <p className="t-wire text-ink-mute">Recommended</p>
      {/* -mx/px pair lets the row bleed to the shell's own edge on a phone --
          a horizontal scroller with hard margins looks clipped rather than
          scrollable. */}
      <div className="-mx-5 mt-4 flex gap-6 overflow-x-auto px-5 pb-2 lg:-mx-12 lg:px-12">
        {stories.map((story) => (
          <div key={story.id} className="w-64 shrink-0 sm:w-72">
            <RecommendedCard story={story} />
          </div>
        ))}
      </div>
    </section>
  );
}
