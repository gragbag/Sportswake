import { NavLink } from "react-router-dom";
import type { CategoryTab } from "../types";

/**
 * Tab bar over the feed.
 *
 * Counts do not sum to the story total, because a story can hold two
 * categories. That is the cost of multi-label and it is the right trade --
 * a tariff announcement genuinely belongs under both Politics and Business.
 *
 * Empty tabs are hidden rather than shown at zero: a tab that leads nowhere
 * reads as broken, and an untagged corpus would render eight of them.
 */
export function CategoryTabs({
  tabs,
  base = "",
}: {
  tabs: CategoryTab[];
  /** Route prefix ("" or "/t/LAL") so tabs stay inside the selected team. */
  base?: string;
}) {
  const populated = tabs.filter((t) => t.count > 0);
  if (populated.length === 0) return null;

  const cls = ({ isActive }: { isActive: boolean }) =>
    `shrink-0 border-b-2 pb-2 text-xs transition-colors ${
      isActive
        ? "border-ink-900 text-ink-900 dark:border-white dark:text-white"
        : "border-transparent text-ink-500 hover:text-ink-900 dark:text-white/50 dark:hover:text-white"
    }`;

  return (
    // Horizontal scroll rather than wrapping: a tab bar that becomes two
    // rows on a narrow screen stops reading as a single control.
    <nav className="mb-6 flex gap-5 overflow-x-auto border-b border-ink-200 dark:border-white/10">
      {/* `end` so "All" is only active on the bare path, not every child. */}
      <NavLink to={base || "/"} end className={cls}>
        All
      </NavLink>
      {populated.map((t) => (
        <NavLink key={t.slug} to={`${base}/c/${t.slug}`} className={cls}>
          {t.label}
          <span className="ml-1.5 tabular-nums text-ink-500 dark:text-white/30">
            {t.count}
          </span>
        </NavLink>
      ))}
    </nav>
  );
}
