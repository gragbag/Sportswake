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
 */
export function TeamPicker() {
  const [teams, setTeams] = useState<TeamOption[] | null>(null);
  const [following, setFollowing] = useState<Set<string> | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/teams")
      .then((r) => r.json())
      .then((all: TeamOption[]) => setTeams(all.filter((t) => t.kind === "team")))
      .catch(() => setTeams([]));

    apiFetch("/api/user-teams")
      .then((r) => (r.ok ? r.json() : []))
      .then((codes: string[]) => setFollowing(new Set(codes)))
      .catch(() => setFollowing(new Set()));
  }, []);

  if (!teams || !following) {
    return <p className="t-caption text-label-3">Loading…</p>;
  }

  async function toggle(code: string) {
    // Optimistic: the set flips immediately and rolls back if the write
    // fails, so picking teams never feels like waiting on a server.
    const next = new Set(following!);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setFollowing(next);
    setSaving(true);

    const res = await apiFetch("/api/user-teams", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes: [...next] }),
    }).catch(() => null);

    if (!res || !res.ok) setFollowing(following!);
    setSaving(false);
  }

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <p className="t-caption text-label-2">
          Teams you follow
        </p>
        <span className="text-xs text-label-3">
          {saving ? "Saving…" : `${following.size} selected`}
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {teams.map((t) => {
          const on = following.has(t.code);
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
      </p>
    </div>
  );
}
