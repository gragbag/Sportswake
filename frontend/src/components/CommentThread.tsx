import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import { CommentNode } from "./CommentNode";
import type { Comment, CommentNodeData } from "../types";

const MAX_LENGTH = 2000;

/**
 * Turn the API's flat list into a tree.
 *
 * The server sorts by score, and building the tree preserves that order
 * within each level because children are appended in the order they arrive.
 * A reply whose parent fell outside the page is promoted to the top level
 * rather than dropped -- losing a comment because its parent paginated away
 * is worse than showing it slightly out of place.
 */
function buildTree(flat: Comment[]): CommentNodeData[] {
  const byId = new Map<string, CommentNodeData>();
  for (const c of flat) byId.set(c.id, { ...c, replies: [] });

  const roots: CommentNodeData[] = [];
  for (const c of flat) {
    const node = byId.get(c.id)!;
    const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
    if (parent) parent.replies.push(node);
    else roots.push(node);
  }
  return roots;
}

export function CommentThread({ storyId }: { storyId: string }) {
  const { session } = useAuth();

  const [comments, setComments] = useState<Comment[] | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    // apiFetch, not fetch: the endpoint takes OPTIONAL auth, so a plain
    // fetch still returns the thread -- but with my_vote 0 on every
    // comment, because the server cannot tell who is asking.
    return apiFetch(`/api/stories/${storyId}/comments`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setComments)
      .catch(() => setComments([]));
  }, [storyId]);

  useEffect(() => {
    setComments(null);
    void load();
    // session matters: signing in mid-page has to refetch, or the thread
    // keeps the signed-out payload where every my_vote is 0.
  }, [load, session]);

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
        // The server's rate-limit and duplicate messages are already
        // written for a human, so surface them rather than inventing a
        // generic failure string.
        const detail = await res.json().then((d) => d.detail).catch(() => null);
        throw new Error(detail ?? `Could not post (HTTP ${res.status})`);
      }
      setBody("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not post");
    } finally {
      setBusy(false);
    }
  }

  const remaining = MAX_LENGTH - body.length;
  const overLimit = remaining < 0;
  const tree = comments ? buildTree(comments) : null;

  return (
    <section className="mt-10">
      <h2 className="text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:text-white/40">
        Discussion{comments && comments.length > 0 ? ` · ${comments.length}` : ""}
      </h2>

      {tree === null ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>
      ) : tree.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500 dark:text-white/50">No comments yet.</p>
      ) : (
        <ol className="mt-3">
          {tree.map((node) => (
            <CommentNode
              key={node.id}
              node={node}
              storyId={storyId}
              onChanged={() => void load()}
            />
          ))}
        </ol>
      )}

      {session ? (
        <form onSubmit={onSubmit} className="mt-6">
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
              className="rounded bg-label px-3 py-1.5 text-xs font-medium text-surface
                         disabled:opacity-40"
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
            {error && <span className="text-[11px] text-red-600">{error}</span>}
          </div>
        </form>
      ) : (
        <p className="mt-6 text-sm text-ink-500 dark:text-white/50">
          <Link to="/login" className="underline">
            Sign in
          </Link>{" "}
          to join the discussion.
        </p>
      )}
    </section>
  );
}
