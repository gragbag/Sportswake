import { useEffect, useState } from "react";
import { readTheme, saveTheme, type Theme } from "../lib/theme";

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: "light", label: "Light", icon: "M8 1v2M8 13v2M15 8h-2M3 8H1M12.7 3.3l-1.4 1.4M4.7 11.3l-1.4 1.4M12.7 12.7l-1.4-1.4M4.7 4.7L3.3 3.3" },
  { value: "system", label: "System", icon: "" },
  { value: "dark", label: "Dark", icon: "M13.5 9.5A5.5 5.5 0 016.5 2.5a5.5 5.5 0 107 7z" },
];

/**
 * Light / System / Dark, as a segmented control.
 *
 * Three options rather than a two-way switch, because "follow my OS" is a
 * real preference and a binary toggle silently overrides it forever after the
 * first tap.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  // Read on mount rather than during render: localStorage is not available
  // during SSR or a static prerender, and this component should never be the
  // reason a build breaks.
  useEffect(() => setTheme(readTheme()), []);

  function choose(next: Theme) {
    setTheme(next);
    saveTheme(next);
  }

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-full bg-fill p-0.5"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => choose(opt.value)}
          aria-pressed={theme === opt.value}
          title={opt.label}
          className={`grid h-7 w-7 place-items-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
            theme === opt.value
              ? "bg-surface text-label shadow-sm"
              : "text-label-3 hover:text-label-2"
          }`}
        >
          {opt.value === "system" ? (
            <svg
              aria-hidden="true"
              viewBox="0 0 16 16"
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="2" y="3" width="12" height="8.5" rx="1.5" />
              <path d="M6 13.5h4" />
            </svg>
          ) : (
            <svg
              aria-hidden="true"
              viewBox="0 0 16 16"
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {opt.value === "light" && <circle cx="8" cy="8" r="3" />}
              <path d={opt.icon} />
            </svg>
          )}
          <span className="sr-only">{opt.label}</span>
        </button>
      ))}
    </div>
  );
}
