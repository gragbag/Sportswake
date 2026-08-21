/**
 * The press furniture, shared.
 *
 * These were local to BriefPage while the brief was the only newsprint route.
 * Every one of them is a house idiom rather than a one-page detail -- a
 * section rule, the way a headline marks itself on hover, the way a whole
 * block becomes one click target -- so a second page reaching for them means
 * they belong in one file rather than copied with a small difference nobody
 * intended.
 */

/**
 * A block-sized click target laid over a composed unit.
 *
 * A <button> cannot legally contain an <h1>, and nesting a heading inside one
 * flattens it out of the accessibility tree anyway -- so the heading stays
 * where it belongs and the target is stretched across the block instead.
 * Anything interactive that must sit ABOVE this needs its own stacking
 * context; see StoryRow, which keeps its star outside the target entirely.
 */
export const TARGET =
  "absolute inset-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[3px] focus-visible:outline-spot";

/**
 * How a headline says it is hoverable: it marks itself, like a proof.
 * Nothing lifts, nothing shades, no fill appears.
 */
export const UNDERLINE =
  "decoration-1 underline-offset-4 group-hover:underline group-has-[:focus-visible]:underline";

/** A section rule: a label, a hairline on the baseline, and a count. */
export function SlugRule({
  label,
  count,
  children,
}: {
  label: string;
  count?: number;
  /** Optional controls, set on the rule to the right of the label. */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-4">
      <p className="t-wire shrink-0 text-ink">{label}</p>
      <span aria-hidden="true" className="anim-rule h-px flex-1 bg-rule" />
      {children}
      {count !== undefined && (
        <p className="t-wire shrink-0 text-ink-mute">{count}</p>
      )}
    </div>
  );
}
