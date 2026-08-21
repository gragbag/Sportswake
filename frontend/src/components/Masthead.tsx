import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

const LINK =
  "hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot";

/**
 * The furniture links, as data.
 *
 * Two branches written out by hand drifted: the signed-out run separated its
 * items with interpuncts and the signed-in run used bare gaps, so the same
 * masthead punctuated itself two ways depending on who was reading it.
 *
 * `lead` is the one item set in full ink -- the action the paper wants from a
 * reader who does not have an account yet.
 */
type NavItem = { to: string; label: string; lead?: boolean };

const ANON: NavItem[] = [
  { to: "/", label: "Brief" },
  { to: "/stories", label: "Stories" },
  { to: "/login", label: "Sign in" },
  { to: "/signup", label: "Get started", lead: true },
];

const MEMBER: NavItem[] = [
  { to: "/", label: "Brief" },
  { to: "/stories", label: "Stories" },
  { to: "/settings", label: "Teams" },
];

/**
 * The flag, which is also the way back.
 *
 * It was a plain span, which was correct for exactly as long as the masthead
 * only ever rendered on the brief -- a flag that links to the page you are
 * already reading is furniture nobody checked. The moment this became the
 * masthead for every page, that assumption turned into a dead end: /stories
 * had no link to "/" anywhere on it, and the only way back to the front page
 * was the browser's back button.
 *
 * Clicking the paper's name to get to the front page is the oldest convention
 * on the web and readers try it first, so it is restored here -- and the nav
 * names the brief as well, because a convention you have to already know is
 * not the same as a way in that you can see.
 */
function Flag({ home }: { home: boolean }) {
  const name = (
    <span className="t-display block text-[1.375rem] text-ink">Sportswake</span>
  );

  if (home) return name;

  return (
    <Link
      to="/"
      aria-label="Sportswake — today's brief"
      className="block decoration-1 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-spot"
    >
      {name}
    </Link>
  );
}

/**
 * The nameplate, over a line of furniture, over a hairline.
 *
 * No sticky blurred bar: a translucent panel floating over newsprint would
 * undo the argument the whole design makes, that depth comes from hairlines
 * and paper tone alone.
 *
 * It used to carry a dateline, and that was the source of most of what was
 * wrong with this corner. The docstring claimed it was "the filed time of the
 * edition on the page, not the clock" -- but generatedAt fell back to
 * new Date(), so on four routes out of six it was exactly the clock it said
 * it was not. And where it WAS a real dateline, the page already printed one:
 * the front page in BriefMeta under the plate, the reading page in its slug
 * line, sign-up in the plate beside the form. Redundant wherever it was true,
 * wrong wherever it was not, and it left the corner as two right-aligned runs
 * of very different lengths with a ragged edge between them. An edition's
 * date belongs with the edition.
 *
 * What is left is a nameplate on its own line and one band of furniture under
 * it: the slogan and the links sharing a baseline, which is what a paper puts
 * beneath its masthead.
 */
export function Masthead() {
  const { email, loading, signOut } = useAuth();
  const { pathname } = useLocation();
  const items = email ? MEMBER : ANON;

  return (
    <header>
      <div className="pt-8 pb-4">
        <Flag home={pathname === "/"} />

        {/* The slogan and the links share one baseline, so the two 11px runs
            read as a single band rather than as two things right-aligned
            against each other across a gap. */}
        <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 pt-2">
          <span className="t-wire text-ink-mute">NBA, every morning</span>

          <nav
            aria-label="Account"
            className="t-wire flex flex-wrap items-center gap-x-3 gap-y-2 text-ink-mute"
          >
            {/* Render nothing rather than a flash of "Sign in" for an
                already-logged-in reader while the session is restored. */}
            {!loading && (
              <>
                {items.map((item, i) => (
                  <Fragment key={item.to}>
                    {i > 0 && (
                      <span aria-hidden="true" className="text-rule">
                        ·
                      </span>
                    )}
                    {/* The page you are already on is set, not linked. A
                        masthead that offers to take you where you are reads
                        as furniture nobody checked. */}
                    {pathname === item.to ? (
                      <span aria-current="page" className="text-ink">
                        {item.label}
                      </span>
                    ) : (
                      <Link
                        to={item.to}
                        className={`${item.lead ? "text-ink " : ""}${LINK}`}
                      >
                        {item.label}
                      </Link>
                    )}
                  </Fragment>
                ))}
                {email && (
                  <>
                    <span aria-hidden="true" className="text-rule">
                      ·
                    </span>
                    <button
                      type="button"
                      onClick={signOut}
                      className={`cursor-pointer ${LINK}`}
                    >
                      Sign out
                    </button>
                  </>
                )}
              </>
            )}
          </nav>
        </div>
      </div>

      <div aria-hidden="true" className="anim-rule h-px w-full bg-rule" />
    </header>
  );
}
