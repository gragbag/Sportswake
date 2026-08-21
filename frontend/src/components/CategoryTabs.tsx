import { Fragment } from "react";
import { NavLink } from "react-router-dom";
import type { CategoryTab } from "../types";

/**
 * The section index, as a run of mono words.
 *
 * Not a tab bar. A tab bar is a control borrowed from an application, and it
 * brought its own furniture with it -- a 2px underline, a bottom border across
 * the page, its own idea of an active colour. A newspaper indexes its sections
 * as a line of type, and the page already has that gesture twice: the masthead
 * sets Day / Auto / Night this way, and the whole design's rule is that the
 * selected thing is simply set in full ink rather than given a pill.
 *
 * Counts do not sum to the story total, because a story can hold two
 * categories. That is the cost of multi-label and it is the right trade -- a
 * tariff announcement genuinely belongs under both Politics and Business.
 *
 * Empty tabs are hidden rather than shown at zero: a tab that leads nowhere
 * reads as broken, and an untagged corpus would render eight of them.
 */
export function CategoryTabs({
  tabs,
  base = "/stories",
}: {
  tabs: CategoryTab[];
  /** Route prefix ("/stories" or "/stories/t/LAL") so the index stays inside
   *  the selected team, rooted wherever the feed lives. */
  base?: string;
}) {
  const populated = tabs.filter((t) => t.count > 0);
  if (populated.length === 0) return null;

  const cls = ({ isActive }: { isActive: boolean }) =>
    `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot ${
      isActive ? "text-ink" : "hover:text-ink"
    }`;

  return (
    // Wraps rather than scrolls. The old bar scrolled horizontally because a
    // tab bar that becomes two rows stops reading as one control -- but a line
    // of section names is not a control, it is a line of type, and the
    // masthead nav above it already wraps the same way.
    <nav
      aria-label="Sections"
      className="t-wire flex flex-wrap items-baseline gap-x-3 gap-y-2 pt-4 text-ink-mute"
    >
      {/* `end` so "All" is only active on the bare path, not every child. */}
      <NavLink to={base} end className={cls}>
        All
      </NavLink>
      {populated.map((t) => (
        <Fragment key={t.slug}>
          <span aria-hidden="true" className="text-rule">
            ·
          </span>
          <NavLink to={`${base}/c/${t.slug}`} className={cls}>
            {t.label}
            <span className="ml-1.5 tabular-nums text-ink-mute">{t.count}</span>
          </NavLink>
        </Fragment>
      ))}
    </nav>
  );
}
