import { useEffect, useState } from "react";
import { apiFetch } from "../lib/auth";
import type { TeamOption } from "../types";

/**
 * Which teams shape your brief.
 *
 * No cap on how many: sections are generated per team whether anyone follows
 * them or not, so following twelve costs nothing. What keeps a brief readable
 * is the render cap and the rule that a team with no news gets no section --
 * not a limit on this list.
 *
 * The chips are mono codes set in reverse type when followed -- marked up,
 * the way a proof is. No colour dot: the code identifies the club better than
 * a swatch does, and thirty brand palettes have no place on a page whose whole
 * argument is that it prints in two colours.
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
    return <p className="t-wire text-ink-mute">Loading…</p>;
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
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <p className="t-wire text-ink">Teams you follow</p>
        <span className="t-wire flex items-center gap-3 text-ink-mute">
          {error && (
            <span className="text-spot">Couldn&rsquo;t save &mdash; try again</span>
          )}
          {!error && !dirty && `${draft.size} selected`}
          {dirty && (
            <button
              onClick={() => {
                setDraft(new Set(saved));
                setError(false);
              }}
              className="cursor-pointer text-ink-mute transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
            >
              Reset
            </button>
          )}
          {(dirty || saving) && (
            <button
              onClick={save}
              disabled={saving}
              className="t-wire cursor-pointer bg-spot px-4 py-2 text-paper transition-opacity hover:opacity-90 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          )}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 pt-1">
        {teams.map((t) => {
          const on = draft.has(t.code);
          return (
            <button
              key={t.code}
              onClick={() => toggle(t.code)}
              aria-pressed={on}
              title={t.name}
              className={`t-wire cursor-pointer border px-2.5 py-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot ${
                on
                  ? "border-ink bg-ink text-paper"
                  : "border-rule text-ink-mute hover:border-ink hover:text-ink"
              }`}
            >
              {t.code}
            </button>
          );
        })}
      </div>

      <p className="t-read mt-4 max-w-[60ch] text-[0.9375rem] text-ink-mute">
        You&rsquo;ll only see a team&rsquo;s section when something actually
        happened &mdash; following more never makes the brief longer by default.
        Changes apply once you save.
      </p>
    </div>
  );
}
