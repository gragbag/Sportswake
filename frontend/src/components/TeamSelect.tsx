import { useNavigate, useParams } from "react-router-dom";
import type { TeamOption } from "../types";

/**
 * Team picker, set on the section rule.
 *
 * Still a native <select>: 30 clubs plus three league scopes do not fit the
 * line-of-type idiom that works for seven categories, and a hand-built
 * listbox would be a keyboard and screen-reader project to reproduce what the
 * platform already does correctly.
 *
 * What changes is everything around it. The bordered, radiused, filled box was
 * the single most "generic web app" object on the page -- so the chrome comes
 * off and the trigger is set as mono type with a mark after it, which is what
 * the rest of the page does with an interactive word. The popup itself is the
 * OS's and is left alone.
 *
 * Navigates rather than holding state, so a team view has a URL that can be
 * shared and hard-refreshed. Switching teams keeps the active category (and
 * vice versa): the two filters compose, per the /t/:team/c/:category route.
 *
 * Entries with zero stories are hidden rather than shown disabled -- an option
 * that leads to an empty feed reads as broken.
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
    navigate(
      code ? `/stories/t/${code}${categoryPath}` : `/stories${categoryPath}`,
    );
  };

  const option = (t: TeamOption) => (
    <option key={t.code} value={t.code}>
      {t.name} ({t.count})
    </option>
  );

  const current = populated.find((t) => t.code === team);

  return (
    // The select is laid over the line invisibly rather than styled in place.
    // A native select takes its width from its WIDEST option, not its selected
    // one, so "All teams" sat in a 200px box and stranded the mark next to it
    // halfway across the rule. Painting our own label and letting the real
    // control cover it keeps the platform's keyboard handling and popup while
    // the line reads as type.
    <label className="t-wire relative flex shrink-0 items-baseline gap-2 text-ink-mute focus-within:outline-2 focus-within:outline-offset-4 focus-within:outline-spot">
      Team
      <span aria-hidden="true" className="text-ink">
        {current ? current.name : "All teams"}
        <span className="pl-1.5 text-ink-mute">▾</span>
      </span>
      <select
        value={team ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
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
