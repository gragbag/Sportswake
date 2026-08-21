import { useState } from "react";
import { apiFetch, useAuth } from "../lib/auth";

function Arrow({ up, filled }: { up: boolean; filled: boolean }) {
  return (
    <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden="true">
      <path
        d={up ? "M6 2l4 5H2z" : "M6 10L2 5h8z"}
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Reddit-style score with up/down arrows.
 *
 * Owns its own score state rather than lifting it: a vote must not reorder
 * the thread under the reader's cursor. The new order appears on the next
 * load, which is what every arrow-based UI does.
 */
export function VoteButtons({
  commentId,
  score: initialScore,
  myVote: initialVote,
}: {
  commentId: string;
  score: number;
  myVote: number;
}) {
  const { session } = useAuth();
  const [score, setScore] = useState(initialScore);
  const [myVote, setMyVote] = useState(initialVote);

  async function cast(value: 1 | -1) {
    if (!session) return;

    // Optimistic. Sending the vote you already hold clears it, so the
    // predicted delta has to account for removing the old one too.
    const previous = { score, myVote };
    const next = myVote === value ? 0 : value;
    setMyVote(next);
    setScore(score - myVote + next);

    try {
      const res = await apiFetch(`/api/comments/${commentId}/vote`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      if (!res.ok) throw new Error(String(res.status));
      // Trust the server's arithmetic over ours -- other people are voting
      // at the same time.
      const data = await res.json();
      setScore(data.score);
      setMyVote(data.my_vote);
    } catch {
      setScore(previous.score);
      setMyVote(previous.myVote);
    }
  }

  const base =
    "cursor-pointer text-ink-mute transition-colors disabled:cursor-default " +
    "disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 " +
    "focus-visible:outline-spot";

  return (
    <div className="flex shrink-0 flex-col items-center gap-0.5">
      <button
        onClick={() => cast(1)}
        disabled={!session}
        aria-label="Upvote"
        aria-pressed={myVote === 1}
        className={`${base} ${myVote === 1 ? "text-spot" : "hover:text-ink"}`}
      >
        <Arrow up filled={myVote === 1} />
      </button>

      <span className="t-wire text-ink">{score}</span>

      <button
        onClick={() => cast(-1)}
        disabled={!session}
        aria-label="Downvote"
        aria-pressed={myVote === -1}
        className={`${base} ${myVote === -1 ? "text-spot" : "hover:text-ink"}`}
      >
        <Arrow up={false} filled={myVote === -1} />
      </button>
    </div>
  );
}
