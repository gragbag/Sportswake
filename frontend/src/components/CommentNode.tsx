import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import { timeAgo } from "../lib/time";
import { VoteButtons } from "./VoteButtons";
import type { CommentNodeData } from "../types";

const MAX_LENGTH = 2000;
const MAX_DEPTH = 3;

/**
 * One comment plus its replies, rendered recursively.
 *
 * A deleted or removed comment still appears when it has replies -- as a
 * tombstone with no author and no text. Dropping it would leave its answers
 * dangling with nothing to answer.
 */
export function CommentNode({
  node,
  storyId,
  onChanged,
}: {
  node: CommentNodeData;
  storyId: string;
  onChanged: () => void;
}) {
  const { session } = useAuth();
  const isMine = session?.user.id === node.user_id;
  const gone = node.status === "deleted" || node.status === "removed";

  const [replying, setReplying] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(url: string, method: string, body: object) {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().then((d) => d.detail).catch(() => null);
        throw new Error(detail ?? `Failed (HTTP ${res.status})`);
      }
      setReplying(false);
      setEditing(false);
      setDraft("");
      // Refetch rather than patching locally: an edit can be moderated into
      // 'removed', and only the server knows that happened.
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  function submitReply(e: FormEvent) {
    e.preventDefault();
    void send(`/api/stories/${storyId}/comments`, "POST", {
      body: draft,
      parent_id: node.id,
    });
  }

  function submitEdit(e: FormEvent) {
    e.preventDefault();
    void send(`/api/comments/${node.id}`, "PATCH", { body: draft });
  }

  async function remove() {
    if (!confirm("Delete this comment? This cannot be undone.")) return;
    setBusy(true);
    try {
      await apiFetch(`/api/comments/${node.id}`, { method: "DELETE" });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="mt-3 first:mt-0">
      <div className="flex gap-3">
        {/* A tombstone has nothing to vote on. */}
        {gone ? (
          <div className="w-4 shrink-0" />
        ) : (
          <VoteButtons
            key={`${node.id}:${node.score}:${node.my_vote}`}
            commentId={node.id}
            score={node.score}
            myVote={node.my_vote}
          />
        )}

        <div className="min-w-0 flex-1">
          {gone ? (
            <p className="text-sm italic text-ink-500 dark:text-white/40">
              {node.status === "deleted" ? "[deleted]" : "[removed]"}
            </p>
          ) : (
            <>
              <div className="flex items-baseline gap-2 text-[11px] text-ink-500 dark:text-white/40">
                <Link
                  to={`/u/${node.author}`}
                  className="font-medium text-ink-900/80 hover:underline dark:text-white/70"
                >
                  {isMine ? "You" : node.author}
                </Link>
                <span>{timeAgo(node.created_at)}</span>
                {node.edited_at && <span>· edited</span>}
              </div>

              {editing ? (
                <form onSubmit={submitEdit} className="mt-1">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={3}
                    maxLength={MAX_LENGTH}
                    className="w-full rounded border border-ink-200 bg-white px-2 py-1 text-sm
                               text-ink-900 outline-none focus:border-ink-500
                               dark:border-white/10 dark:bg-white/5 dark:text-white"
                  />
                  <div className="mt-1 flex gap-2 text-[11px]">
                    <button
                      type="submit"
                      disabled={busy || !draft.trim()}
                      className="underline disabled:opacity-40"
                    >
                      Save
                    </button>
                    <button type="button" onClick={() => setEditing(false)} className="underline">
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-ink-900 dark:text-white/90">
                  {node.body}
                </p>
              )}
            </>
          )}

          <div className="mt-1 flex gap-3 text-[11px] text-ink-500 dark:text-white/40">
            {/* Replies stop at the depth cap -- offering a button that
                always 422s would be worse than not offering one. */}
            {session && !editing && node.depth < MAX_DEPTH && (
              <button onClick={() => setReplying(!replying)} className="hover:underline">
                {replying ? "Cancel" : "Reply"}
              </button>
            )}
            {isMine && !gone && !editing && (
              <>
                <button
                  onClick={() => {
                    setDraft(node.body ?? "");
                    setEditing(true);
                  }}
                  className="hover:underline"
                >
                  Edit
                </button>
                <button onClick={() => void remove()} disabled={busy} className="hover:underline">
                  Delete
                </button>
              </>
            )}
            {error && <span className="text-red-600">{error}</span>}
          </div>

          {replying && (
            <form onSubmit={submitReply} className="mt-2">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                rows={2}
                maxLength={MAX_LENGTH}
                placeholder="Reply"
                className="w-full rounded border border-ink-200 bg-white px-2 py-1 text-sm
                           text-ink-900 outline-none focus:border-ink-500
                           dark:border-white/10 dark:bg-white/5 dark:text-white"
              />
              <button
                type="submit"
                disabled={busy || !draft.trim()}
                className="mt-1 rounded bg-label px-2 py-1 text-[11px] font-medium text-surface
                           disabled:opacity-40"
              >
                {busy ? "Posting…" : "Reply"}
              </button>
            </form>
          )}

          {node.replies.length > 0 && (
            // Indent with a rule rather than margin alone: at depth 3 the
            // nesting is hard to follow without a visible spine.
            <ol className="mt-2 border-l border-ink-200 pl-3 dark:border-white/10">
              {node.replies.map((child) => (
                <CommentNode
                  key={child.id}
                  node={child}
                  storyId={storyId}
                  onChanged={onChanged}
                />
              ))}
            </ol>
          )}
        </div>
      </div>
    </li>
  );
}
