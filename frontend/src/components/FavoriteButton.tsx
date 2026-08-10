import type { MouseEvent } from "react";
import { useAuth } from "../lib/auth";
import { useFavorites } from "../lib/favorites";

/**
 * Star toggle. Renders nothing when signed out -- an inert star that prompts
 * a login on click is a worse experience than no star at all.
 */
export function FavoriteButton({ storyId }: { storyId: string }) {
  const { session } = useAuth();
  const { isFavorite, toggle } = useFavorites();

  if (!session) return null;

  const saved = isFavorite(storyId);

  function onClick(e: MouseEvent) {
    // Cards are wrapped in a <Link>, so without these the click navigates to
    // the story instead of toggling.
    e.preventDefault();
    e.stopPropagation();
    void toggle(storyId);
  }

  return (
    <button
      onClick={onClick}
      aria-pressed={saved}
      aria-label={saved ? "Remove from favorites" : "Save to favorites"}
      title={saved ? "Remove from favorites" : "Save to favorites"}
      className="shrink-0 text-ink-500 transition-colors hover:text-ink-900
                 dark:text-white/40 dark:hover:text-white"
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
        <path
          d="M10 2.5l2.35 4.76 5.25.76-3.8 3.7.9 5.23L10 14.5l-4.7 2.47.9-5.23-3.8-3.7 5.25-.76z"
          // Filled when saved, outline when not -- state is legible without
          // relying on colour alone.
          fill={saved ? "currentColor" : "none"}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
