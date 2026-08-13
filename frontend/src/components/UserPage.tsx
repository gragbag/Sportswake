import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../lib/auth";
import { timeAgo } from "../lib/time";
import { VoteButtons } from "./VoteButtons";
import type { PublicProfile } from "../types";

export function UserPage() {
  const { handle } = useParams();
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProfile(null);
    setError(null);
    // apiFetch, not fetch: the endpoint reads the token when present so you
    // can see your own hidden history and your own votes render filled.
    apiFetch(`/api/users/${handle}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setProfile)
      .catch(() => setError("No such user"));
  }, [handle]);

  if (error) {
    return (
      <div className="text-sm text-ink-500 dark:text-white/50">
        <p>{error}.</p>
        <Link to="/" className="mt-2 inline-block underline">
          Back to all stories
        </Link>
      </div>
    );
  }

  if (!profile) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold text-ink-900 dark:text-white">
        {profile.handle}
      </h1>
      <p className="mt-1 text-xs text-ink-500 dark:text-white/50">
        {profile.joined_at
          ? `Joined ${new Date(profile.joined_at).toLocaleDateString()}`
          : "No profile set up"}
        {profile.is_self && profile.history_hidden && " · your history is hidden from others"}
      </p>

      <h2 className="mt-8 text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:text-white/40">
        Comments
      </h2>

      {profile.history_hidden && !profile.is_self ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">
          This user has chosen not to show their comment history.
        </p>
      ) : profile.comments.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">
          No comments yet.
        </p>
      ) : (
        <ol className="mt-3">
          {profile.comments.map((c) => (
            <li
              key={c.id}
              className="flex gap-3 border-b border-ink-200 py-3 last:border-0 dark:border-white/10"
            >
              {/* key includes the server's numbers so a refetch REMOUNTS this
                  and resets its internal state. Without it the component
                  keeps the score it mounted with -- signing in would leave
                  every arrow empty. */}
              <VoteButtons
                key={`${c.id}:${c.score}:${c.my_vote}`}
                commentId={c.id}
                score={c.score}
                myVote={c.my_vote}
              />
              <div className="min-w-0">
                {/* The story is the context -- a comment on its own reads as
                    a fragment. */}
                <Link
                  to={`/story/${c.story_id}`}
                  className="text-[11px] text-ink-500 hover:underline dark:text-white/40"
                >
                  {c.story_title}
                </Link>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-900 dark:text-white/90">
                  {c.body}
                </p>
                <div className="mt-1 text-[11px] text-ink-500 dark:text-white/40">
                  {timeAgo(c.created_at)}
                  {c.edited_at && " · edited"}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
