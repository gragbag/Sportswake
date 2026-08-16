import type { Team } from "../types";

/**
 * Rank-ordered team badges, shared by the feed card and the story page for
 * the same no-drift reason as CategoryPills.
 *
 * Circles, sized like the logo badges every sports site trains readers on,
 * with the three-letter code inside and the full name on hover. Rank 0
 * renders first -- whose story it mostly is. Filled where the category
 * pills are outlined: who a story is about outranks what kind it is.
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
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {teams.map((team) => (
        <span
          key={team.code}
          title={team.name}
          // Club codes are three characters and fit a true circle; the
          // scope codes (EAST, WEST, LEAGUE) are longer and become a
          // lozenge -- the schema's length-tells-kind trick, visually.
          className={`flex h-8 items-center justify-center rounded-full
                     border border-ink-900/25 bg-ink-50 text-[9px] font-bold
                     tracking-wide text-ink-900/80 dark:border-white/30
                     dark:bg-white/10 dark:text-white/80 ${
                       team.code.length === 3 ? "w-8" : "px-2.5"
                     }`}
        >
          {team.code}
        </span>
      ))}
    </div>
  );
}
