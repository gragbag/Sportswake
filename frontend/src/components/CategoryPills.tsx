import type { Category } from "../types";

/**
 * Rank-ordered category badges, shared by the feed card and the story page so
 * the two cannot drift apart.
 *
 * Outlined pills rather than the filled chips used for outlets and people:
 * three filled rows on one card would read as one list of the same kind of
 * thing. Renders nothing when a story is untagged, which is the normal state
 * for most of the corpus rather than an error.
 *
 * Deliberately not links. A card is already wrapped in an <a>, and a nested
 * anchor is invalid HTML that React Router will not route -- so making these
 * navigate to /c/:slug means giving the card and the page different markup,
 * which is the drift this component exists to prevent.
 */
export function CategoryPills({
  categories,
  className = "",
}: {
  categories: Category[];
  className?: string;
}) {
  if (categories.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {categories.map((category) => (
        <span
          key={category.slug}
          className="rounded-full border border-ink-200 px-2 py-0.5 text-[10px]
                     font-medium uppercase tracking-wide text-ink-500
                     dark:border-white/15 dark:text-white/50"
        >
          {category.label}
        </span>
      ))}
    </div>
  );
}
