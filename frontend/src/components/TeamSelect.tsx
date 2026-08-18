import { useNavigate, useParams } from "react-router-dom";
import type { TeamOption } from "../types";

/**
 * Team picker over the feed. A dropdown, not a tab row: 30 clubs plus three
 * league scopes do not fit the tab idiom that works for seven categories.
 *
 * Navigates rather than holding state, so a team view has a URL that can be
 * shared and hard-refreshed -- the same reason the category tabs are links.
 * Switching teams keeps the active category (and vice versa): the two filters
 * compose, per the /t/:team/c/:category route.
 *
 * Like the tabs, entries with zero stories are hidden rather than shown
 * disabled -- an option that leads to an empty feed reads as broken, and an
 * untagged corpus would render 33 of them.
 */
export function TeamSelect({ teams }: { teams: TeamOption[] }) {
  const { team, category } = useParams();
  const navigate = useNavigate();

  const populated = teams.filter((t) => t.count > 0);
  if (populated.length === 0) return null;

  // Scopes keep their seed order (League, East, West); clubs read faster
  // alphabetically than in the seed's division order.
  const scopes = populated.filter((t) => t.kind !== "team");
  const clubs = populated
    .filter((t) => t.kind === "team")
    .sort((a, b) => a.name.localeCompare(b.name));

  const onChange = (code: string) => {
    // Rooted at /stories since the brief took over "/".
    const categoryPath = category ? `/c/${category}` : "";
    navigate(
      code ? `/stories/t/${code}${categoryPath}` : `/stories${categoryPath}`,
    );
  };

  const option = (t: TeamOption) => (
    <option key={t.code} value={t.code}>
      {t.name} ({t.count})
    </option>
  );

  return (
    // The select uses role tokens with no dark: overrides -- surface and
    // label flip with the theme on their own. Its old classes hardcoded
    // bg-white and used ink-900 as a DARK BACKGROUND, which broke when the
    // legacy ink scale was remapped onto role colors: ink-900 is the label
    // color now, and labels go light in dark mode.
    <label className="mb-4 flex items-center gap-2 text-xs text-ink-500 dark:text-white/50">
      Team
      <select
        value={team ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-separator bg-surface px-2 py-1
                   text-xs text-label"
      >
        <option value="">All teams</option>
        {scopes.length > 0 && (
          <optgroup label="League">{scopes.map(option)}</optgroup>
        )}
        {clubs.length > 0 && (
          <optgroup label="Teams">{clubs.map(option)}</optgroup>
        )}
      </select>
    </label>
  );
}
