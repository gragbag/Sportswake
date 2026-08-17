import { minutes } from "../lib/edition";
import type { BriefSection } from "../types";

function snippet(text: string, chars = 128): string {
  const flat = text.replace(/\*+/g, "").replace(/\s+/g, " ").trim();
  if (flat.length <= chars) return flat;
  const cut = flat.slice(0, chars);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

/**
 * One team's section, as a take on a wire printout.
 *
 * Rows are separated by hairlines and nothing else -- no container, no fill,
 * no radius -- so the list reads as one column of copy with divisions rather
 * than a stack of cards. Hover marks the headline rather than shading the row,
 * which is the same gesture the plates use.
 *
 * The team is identified by its code, set in mono, not by a colour chip. A
 * three-letter slug is what a wire service actually puts in front of a take,
 * it is more informative than a dot, and it keeps thirty brand palettes off a
 * page whose entire argument is that it prints in two colours.
 */
export function SectionRow({
  section,
  onOpen,
}: {
  section: BriefSection;
  onOpen: () => void;
}) {
  return (
    <li className="group border-t border-rule">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full cursor-pointer items-baseline gap-4 py-4 text-left focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-spot"
      >
        <span className="t-wire w-10 shrink-0 text-ink-mute">
          {section.team}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="t-display text-[1.125rem] text-ink decoration-1 underline-offset-4 group-hover:underline group-has-[:focus-visible]:underline">
              {section.team_name}
            </span>
            {section.is_major && (
              <span className="t-wire text-ink">Major</span>
            )}
          </span>
          <span className="t-read mt-1.5 block text-ink-mute">
            {snippet(section.body_md)}
          </span>
        </span>

        <span className="t-wire shrink-0 text-ink-mute">
          {minutes(section.word_count)} min
        </span>
      </button>
    </li>
  );
}
