import type { Team } from "../types";

/**
 * Rank-ordered team badges, shared by the feed card and the story page for
 * the same no-drift reason as CategoryPills.
 *
 * Shows the three-letter code with the full name on hover: LAL is how fans
 * already read team references, and full names would crowd a card that can
 * carry three of them plus two categories. Darker text than the category
 * pills on purpose -- who a story is about outranks what kind it is.
 *
 * Not links, for the same nested-anchor reason as CategoryPills.
 */
export function TeamPills({
  teams,
  className = "",
}: {
  teams: Team[];
  className?: string;
}) {
  if (teams.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {teams.map((team) => (
        <span
          key={team.code}
          title={team.name}
          className="rounded-full border border-ink-900/25 px-2 py-0.5
                     text-[10px] font-semibold uppercase tracking-wide
                     text-ink-900/80 dark:border-white/30 dark:text-white/80"
        >
          {team.code}
        </span>
      ))}
    </div>
  );
}
