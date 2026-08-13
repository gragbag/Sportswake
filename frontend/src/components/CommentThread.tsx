import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import { timeAgo } from "../lib/time";
import type { Comment } from "../types";

const MAX_LENGTH = 2000;

export function CommentThread({ storyId }: { storyId: string }) {
  const { session } = useAuth();
  const selfId = session?.user.id;

  const [comments, setComments] = useState<Comment[] | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setComments(null);
    fetch(`/api/stories/${storyId}/comments`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setComments)
      .catch(() => setComments([]));
  }, [storyId]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);

    try {
      const res = await apiFetch(`/api/stories/${storyId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body }),
      });

      if (!res.ok) {
        // The server's rate-limit and duplicate messages are already written
        // for a human ("limit is 3 comments per hour"), so surface them
        // rather than inventing a generic failure string.
        const detail = await res
          .json()
          .then((d) => d.detail)
          .catch(() => null);
        throw new Error(detail ?? `Could not post (HTTP ${res.status})`);
      }

      // Append the row the server actually created rather than guessing at
      // it: moderation may eventually hold a comment, and the response is
      // the only thing that knows.
      const created: Comment = await res.json();
      setComments((prev) => [...(prev ?? []), created]);
      setBody("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not post");
    } finally {
      setBusy(false);
    }
  }

  const remaining = MAX_LENGTH - body.length;
  const overLimit = remaining < 0;

  return (
    <section className="mt-10">
      <h2 className="text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:text-white/40">
        Discussion{comments && comments.length > 0 ? ` · ${comments.length}` : ""}
      </h2>

      {comments === null ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>
      ) : comments.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">
          No comments yet.
        </p>
      ) : (
        <ol className="mt-3">
          {comments.map((c) => (
            <li
              key={c.id}
              className="border-b border-ink-200 py-3 last:border-0 dark:border-white/10"
            >
              <div className="flex items-baseline gap-2 text-[11px] text-ink-500 dark:text-white/40">
                <span className="font-medium text-ink-900/80 dark:text-white/70">
                  {c.user_id === selfId ? "You" : c.author}
                </span>
                <span>{timeAgo(c.created_at)}</span>
                {c.edited_at && <span>· edited</span>}
              </div>
              {/* whitespace-pre-wrap keeps the author's line breaks; without
                  it every paragraph collapses into one run of text. */}
              <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-900 dark:text-white/90">
                {c.body}
              </p>
            </li>
          ))}
        </ol>
      )}

      {session ? (
        <form onSubmit={onSubmit} className="mt-4">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            placeholder="Add a comment"
            className="w-full rounded border border-ink-200 bg-white px-3 py-2 text-sm
                       text-ink-900 outline-none focus:border-ink-500
                       dark:border-white/10 dark:bg-white/5 dark:text-white"
          />

          <div className="mt-2 flex items-center gap-3">
            <button
              type="submit"
              disabled={busy || !body.trim() || overLimit}
              className="rounded bg-ink-900 px-3 py-1.5 text-xs font-medium text-white
                         disabled:opacity-40 dark:bg-white dark:text-ink-900"
            >
              {busy ? "Posting…" : "Post"}
            </button>

            {/* Only shown near the limit -- a counter that is always visible
                reads as a warning when nothing is wrong. */}
            {remaining < 200 && (
              <span
                className={`text-[11px] tabular-nums ${
                  overLimit ? "text-red-600" : "text-ink-500 dark:text-white/40"
                }`}
              >
                {remaining}
              </span>
            )}

            {error && (
              <span className="text-[11px] text-red-600">{error}</span>
            )}
          </div>
        </form>
      ) : (
        <p className="mt-4 text-sm text-ink-500 dark:text-white/50">
          <Link to="/login" className="underline">
            Sign in
          </Link>{" "}
          to join the discussion.
        </p>
      )}
    </section>
  );
}
