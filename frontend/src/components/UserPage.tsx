import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../lib/auth";
import { timeAgo } from "../lib/time";
import { VoteButtons } from "./VoteButtons";
import { SlugRule } from "./press";
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
      <div className="pt-8">
        <h1 className="t-display text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          {error}.
        </h1>
        <Link
          to="/stories"
          className="t-wire mt-6 inline-block border-b border-spot pb-1 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
        >
          All stories
        </Link>
      </div>
    );
  }

  if (!profile) {
    return <p className="t-wire pt-8 text-ink-mute">Loading&hellip;</p>;
  }

  return (
    <div className="max-w-[68ch] pt-8">
      <h1 className="t-display text-[clamp(1.75rem,4vw,2.5rem)] leading-[1.02]">
        {profile.handle}
      </h1>
      <p className="t-wire pt-3 text-ink-mute">
        {profile.joined_at
          ? `Joined ${new Date(profile.joined_at).toLocaleDateString()}`
          : "No profile set up"}
        {profile.is_self && profile.history_hidden && " · your history is hidden from others"}
      </p>

      <div className="pt-10">
        <SlugRule
          label="Comments"
          count={profile.comments.length > 0 ? profile.comments.length : undefined}
        />
      </div>

      {profile.history_hidden && !profile.is_self ? (
        <p className="t-read pt-6 text-ink-mute">
          This user has chosen not to show their comment history.
        </p>
      ) : profile.comments.length === 0 ? (
        <p className="t-read pt-6 text-ink-mute">No comments yet.</p>
      ) : (
        <ol className="pt-2">
          {profile.comments.map((c) => (
            <li
              key={c.id}
              className="flex gap-4 border-t border-rule py-4"
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
                  className="t-wire text-ink-mute hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
                >
                  {c.story_title}
                </Link>
                <p className="t-read mt-1.5 whitespace-pre-wrap text-ink">
                  {c.body}
                </p>
                <div className="t-wire mt-2 text-ink-mute">
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
