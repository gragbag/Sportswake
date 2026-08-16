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
    const categoryPath = category ? `/c/${category}` : "";
    navigate(code ? `/t/${code}${categoryPath}` : categoryPath || "/");
  };

  const option = (t: TeamOption) => (
    <option key={t.code} value={t.code}>
      {t.name} ({t.count})
    </option>
  );

  return (
    <label className="mb-4 flex items-center gap-2 text-xs text-ink-500 dark:text-white/50">
      Team
      <select
        value={team ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-ink-200 bg-white px-2 py-1 text-xs
                   text-ink-900 dark:border-white/15 dark:bg-ink-900
                   dark:text-white"
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
