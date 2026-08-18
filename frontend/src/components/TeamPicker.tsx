import { useEffect, useState } from "react";
import { apiFetch } from "../lib/auth";
import { teamColor } from "../lib/teamColors";
import type { TeamOption } from "../types";

/**
 * Which teams shape your brief.
 *
 * No cap on how many: sections are generated per team whether anyone follows
 * them or not, so following twelve costs nothing. What keeps a brief readable
 * is the render cap and the rule that a team with no news gets no section --
 * not a limit on this list.
 *
 * Draft-then-Save, not save-per-toggle. Toggling is pure local state; nothing
 * touches the network until Save, so a sixteen-click session is one PUT
 * instead of sixteen racing ones. The races the old optimistic version had --
 * overlapping full-set PUTs committing out of click order, a failed write
 * rolling back to a stale closure -- are impossible when there is only ever
 * one write in flight and it carries the whole draft.
 */
export function TeamPicker() {
  const [teams, setTeams] = useState<TeamOption[] | null>(null);
  /** What the server currently holds -- the baseline Save is measured against. */
  const [saved, setSaved] = useState<Set<string> | null>(null);
  /** The local draft the chips edit. */
  const [draft, setDraft] = useState<Set<string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/api/teams")
      .then((r) => r.json())
      .then((all: TeamOption[]) => setTeams(all.filter((t) => t.kind === "team")))
      .catch(() => setTeams([]));

    apiFetch("/api/user-teams")
      .then((r) => (r.ok ? r.json() : []))
      .then((codes: string[]) => {
        setSaved(new Set(codes));
        setDraft(new Set(codes));
      })
      .catch(() => {
        setSaved(new Set());
        setDraft(new Set());
      });
  }, []);

  if (!teams || !draft || !saved) {
    return <p className="t-caption text-label-3">Loading…</p>;
  }

  function toggle(code: string) {
    const next = new Set(draft!);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setDraft(next);
    setError(false);
  }

  const dirty =
    draft.size !== saved.size || [...draft].some((c) => !saved.has(c));

  async function save() {
    setSaving(true);
    setError(false);
    const res = await apiFetch("/api/user-teams", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes: [...draft!] }),
    }).catch(() => null);
    setSaving(false);

    if (!res || !res.ok) {
      // The draft is kept: the reader's picks are the thing worth not
      // losing, and Save can simply be pressed again.
      setError(true);
      return;
    }
    // The server answers with what it actually stored (validation happens
    // there), so the baseline comes from the response, not the draft.
    const body: { following: string[] } = await res.json();
    setSaved(new Set(body.following));
    setDraft(new Set(body.following));
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="t-caption text-label-2">Teams you follow</p>
        <span className="flex items-center gap-2 text-xs text-label-3">
          {error && (
            <span className="text-red-600 dark:text-red-400">
              Couldn&rsquo;t save &mdash; try again
            </span>
          )}
          {!error && !dirty && `${draft.size} selected`}
          {dirty && (
            <button
              onClick={() => {
                setDraft(new Set(saved));
                setError(false);
              }}
              className="rounded-full px-2 py-1 text-label-3 transition-colors hover:text-label focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Reset
            </button>
          )}
          {(dirty || saving) && (
            <button
              onClick={save}
              disabled={saving}
              className="t-footnote rounded-full bg-accent px-3.5 py-1.5 font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          )}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {teams.map((t) => {
          const on = draft.has(t.code);
          return (
            <button
              key={t.code}
              onClick={() => toggle(t.code)}
              aria-pressed={on}
              title={t.name}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                on
                  ? "border-accent bg-accent text-white"
                  : "border-separator text-label-2 hover:border-label-3 dark:hover:border-label-3"
              }`}
            >
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: on ? "currentColor" : teamColor(t.code) }}
              />
              {t.code}
            </button>
          );
        })}
      </div>

      <p className="mt-3 text-xs text-label-3">
        You&rsquo;ll only see a team&rsquo;s section when something actually
        happened &mdash; following more never makes the brief longer by default.
        Changes apply once you save.
      </p>
    </div>
  );
}
