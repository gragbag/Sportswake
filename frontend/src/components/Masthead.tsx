import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { formatClock, formatDayStamp } from "../lib/dateline";
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
 * second accent, since the spot budget on this page is already spent on the
 * freshness rule, the live square and the focus ring.
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
 * The flag and the dateline, over a hairline.
 *
 * A masthead, so it carries the paper's furniture as well as its name: the
 * account links and the press run sit up here in mono, quiet enough to ignore
 * and findable when wanted. That is why this page does not use the app's
 * sticky blurred bar -- a translucent panel floating over newsprint would
 * undo the argument the whole page is making, that depth comes from hairlines
 * and paper tone alone.
 *
 * The dateline is the filed time of the edition on the page, not the clock: a
 * masthead carries the date of what is printed beneath it.
 */
export function Masthead({
  generatedAt,
  stale,
}: {
  generatedAt: string | null;
  stale?: boolean;
}) {
  const { email, loading, signOut } = useAuth();
  const stamp = generatedAt ?? new Date().toISOString();

  return (
    <header>
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-4 pt-8 pb-4">
        <div>
          <span className="t-display block text-[1.375rem] text-ink">
            Sportswake
          </span>
          <span className="t-wire mt-1 block text-ink-mute">
            NBA, three times a day
          </span>
        </div>

        <div className="flex flex-col gap-2 sm:items-end">
          <time className="t-wire text-ink-mute" dateTime={stamp}>
            {formatDayStamp(stamp)}
            <span aria-hidden="true"> · </span>
            {formatClock(stamp)}
            {stale && (
              <>
                <span aria-hidden="true"> · </span>
                most recent
              </>
            )}
          </time>

          <nav
            aria-label="Account"
            className="t-wire flex flex-wrap items-center gap-x-3 gap-y-2 text-ink-mute"
          >
            {/* Render nothing rather than a flash of "Sign in" for an
                already-logged-in reader while the session is restored. */}
            {!loading &&
              (email ? (
                <>
                  <Link to="/settings" className={LINK}>
                    Teams
                  </Link>
                  <button
                    type="button"
                    onClick={signOut}
                    className={`cursor-pointer ${LINK}`}
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link to="/login" className={LINK}>
                    Sign in
                  </Link>
                  <span aria-hidden="true" className="text-rule">
                    ·
                  </span>
                  <Link to="/signup" className={`text-ink ${LINK}`}>
                    Get started
                  </Link>
                </>
              ))}
            <span aria-hidden="true" className="text-rule">
              |
            </span>
            <PressRun />
          </nav>
        </div>
      </div>

      <div aria-hidden="true" className="anim-rule h-px w-full bg-rule" />
    </header>
  );
}
