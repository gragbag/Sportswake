import { useEffect, useState } from "react";
import { readTheme, saveTheme, type Theme } from "../lib/theme";

const LINK =
  "hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot";

const THEMES: { value: Theme; label: string }[] = [
  { value: "light", label: "Day" },
  { value: "system", label: "Auto" },
  { value: "dark", label: "Night" },
];

/**
 * Day / Auto / Night, as three words on a rule.
 *
 * Three options rather than a two-way switch, because "follow my OS" is a real
 * preference and a binary toggle silently overrides it forever after the first
 * tap. The selected one is simply set in full ink -- no pill, no fill, no
 * second accent.
 */
function PressRun() {
  const [theme, setTheme] = useState<Theme>("system");

  // Read on mount rather than during render: localStorage is not available
  // during a static prerender, and this should never be why a build breaks.
  useEffect(() => setTheme(readTheme()), []);

  return (
    <div role="group" aria-label="Colour theme" className="flex items-center">
      {THEMES.map(({ value, label }, i) => (
        <span key={value} className="flex items-center">
          {i > 0 && (
            <span aria-hidden="true" className="px-1.5 text-rule">
              /
            </span>
          )}
          <button
            type="button"
            aria-pressed={theme === value}
            onClick={() => {
              setTheme(value);
              saveTheme(value);
            }}
            className={`cursor-pointer ${LINK} ${
              theme === value ? "text-ink" : ""
            }`}
          >
            {label}
          </button>
        </span>
      ))}
    </div>
  );
}

/**
 * The foot of the paper.
 *
 * The press run lived in the masthead, which put a preference somebody sets
 * once beside the four links they use every visit. Seven interactive words in
 * one line, punctuated three different ways -- interpuncts between the links,
 * a pipe before the theme, slashes inside it -- and the corner read as noise
 * rather than as navigation.
 *
 * A colophon is where a paper has always put how it was produced, and the
 * press run is exactly that: not news, not navigation, findable when wanted.
 * Moving it here leaves the masthead with one kind of separator and four
 * words.
 */
export function Colophon() {
  return (
    <footer className="t-wire mt-16 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3 border-t border-rule pt-5 text-ink-mute">
      <p>
        Sportswake
        <span aria-hidden="true"> · </span>
        NBA, every morning
        <span aria-hidden="true"> · </span>
        Summaries are AI-generated and always marked
      </p>
      <PressRun />
    </footer>
  );
}
