import { useState } from "react";
import { apiFetch, useAuth } from "../lib/auth";
import type { Reactions } from "../types";

const REACTIONS: { key: keyof Reactions; emoji: string; label: string }[] = [
  { key: "like", emoji: "👍", label: "Like" },
  { key: "dislike", emoji: "👎", label: "Dislike" },
  { key: "happy", emoji: "😄", label: "Happy" },
  { key: "sad", emoji: "😢", label: "Sad" },
  { key: "angry", emoji: "😠", label: "Angry" },
];

/**
 * One reaction per reader, click-to-set / click-again-to-clear -- same rule
 * comment voting already follows, one level up.
 *
 * Optimistic, same pattern FavoritesProvider already uses for the star: the
 * click updates the screen immediately and reconciles with the server in the
 * background, rolling back only on failure. This is what actually fixes the
 * felt lag -- every write here crosses to Supabase, measured at ~450ms round
 * trip in dev, and no amount of trimming the query removes a network hop the
 * reader is sitting in front of. Making the click free of that wait is the
 * fix; the server call still happens, it just no longer gates the UI.
 *
 * Engagement only. This does not feed personalization: a reaction tracks how
 * a reader feels about the EVENT, not whether they want more of that team's
 * coverage, and for a fan those point opposite ways -- a bad-news story about
 * your team draws your strongest reaction, not your disinterest. Favorites
 * and follows stay what drives recommendations; this is the reader's voice,
 * no more.
 *
 * Renders nothing when signed out, same as FavoriteButton -- an inert row of
 * emoji that prompts a login on click is a worse experience than no row.
 */
export function ReactionBar({
  storyId,
  reactions: initial,
  myReaction: initialMine,
}: {
  storyId: string;
  reactions: Reactions;
  myReaction: string | null;
}) {
  const { session } = useAuth();
  // Seeded from the story fetch, then owned locally -- nothing else on the
  // page needs to know about a reaction change, so there is nothing to lift
  // this state up to.
  const [reactions, setReactions] = useState(initial);
  const [mine, setMine] = useState(initialMine);

  if (!session) return null;

  function react(key: string) {
    const wasMine = mine;
    const clearing = wasMine === key;

    // Flip the screen now, from what is already known client-side -- the
    // server call below exists to persist this, not to compute it, so
    // nothing here waits on it.
    setReactions((prev) => {
      const next = { ...prev };
      if (wasMine) next[wasMine as keyof Reactions] -= 1;
      if (!clearing) next[key as keyof Reactions] += 1;
      return next;
    });
    setMine(clearing ? null : key);

    const request = clearing
      ? apiFetch(`/api/stories/${storyId}/reaction`, { method: "DELETE" })
      : apiFetch(`/api/stories/${storyId}/reaction`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reaction: key }),
        });

    request
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((body: { reactions: Reactions; my_reaction: string | null }) => {
        // The server's counts are the truth -- a second tab reacting to the
        // same story in between would otherwise never show up here.
        setReactions(body.reactions);
        setMine(body.my_reaction);
      })
      .catch(() => {
        // Undo exactly THIS click's delta, via a functional updater rather
        // than restoring a snapshot -- reactions can compound (a second
        // click can land while the first is still in flight), and stomping
        // back to how things looked before this click started would also
        // erase whichever of those already succeeded.
        setReactions((prev) => {
          const next = { ...prev };
          if (!clearing) next[key as keyof Reactions] -= 1;
          if (wasMine) next[wasMine as keyof Reactions] += 1;
          return next;
        });
        setMine(wasMine);
      });
  }

  return (
    <div
      role="group"
      aria-label="React to this story"
      className="flex flex-wrap items-center gap-1.5 pt-4"
    >
      {REACTIONS.map(({ key, emoji, label }) => {
        const active = mine === key;
        const count = reactions[key];
        return (
          <button
            key={key}
            onClick={() => react(key)}
            aria-pressed={active}
            title={label}
            className={`flex cursor-pointer items-center gap-1 rounded-full
                       border px-2.5 py-1 text-sm transition-colors
                       focus-visible:outline-2 focus-visible:outline-offset-2
                       focus-visible:outline-spot ${
                         active
                           ? "border-spot bg-spot/10 text-spot"
                           : "border-rule text-ink-mute hover:border-ink hover:text-ink"
                       }`}
          >
            <span aria-hidden="true">{emoji}</span>
            {count > 0 && <span className="t-wire tabular-nums">{count}</span>}
          </button>
        );
      })}
    </div>
  );
}
