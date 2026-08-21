import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/auth";
import { editionFromBrief, editionWindow, type Edition } from "../lib/edition";
import type { Brief } from "../types";
import { BriefMeta } from "./BriefMeta";
import { BriefPlate } from "./BriefPlate";
import { UNDERLINE } from "./press";

/**
 * Today's edition, printed next to the form.
 *
 * Nobody signs up for an account. They sign up for the thing on the left, and
 * the sign-up page was the one place in the product that never showed it -- a
 * headline, a contents block and a freshness rule say what this is in a way
 * that no amount of benefit copy does.
 *
 * It is decoration in the strict sense that the page works without it, so it
 * is built to fail silently: no skeleton, no error state, no spinner. If the
 * wire is down the reader gets a sign-up form, which is what they came for.
 * The form never waits on this.
 */
export function LatestPlate() {
  const [edition, setEdition] = useState<Edition | null>(null);
  const [windowMs, setWindowMs] = useState(24 * 3_600_000);

  useEffect(() => {
    // Guarded against a unmount mid-flight: this sits on a page whose whole
    // purpose is to navigate away.
    let alive = true;
    apiFetch(`/api/brief?local_hour=${new Date().getHours()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((brief: Brief) => {
        if (!alive) return;
        // is_stale means the served edition is not today's, which is exactly
        // when the freshness rule must not claim to be live.
        const next = editionFromBrief(brief, !brief.is_stale);
        if (next) {
          setEdition(next);
          setWindowMs(editionWindow(brief.available_slots));
        }
      })
      .catch(() => {
        /* the page is a sign-up form first; the plate is the argument for it */
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!edition) return null;

  return (
    <aside className="pt-12">
      <p className="t-wire pb-3 text-ink-mute">Today’s edition</p>
      <Link
        to="/"
        className="group block focus-visible:outline-2 focus-visible:outline-offset-[3px] focus-visible:outline-spot"
      >
        <BriefPlate edition={edition} variant="lead" windowMs={windowMs} />
        <div className="pt-4">
          <BriefMeta edition={edition} />
        </div>
        <h2
          className={`t-display pt-2 text-[clamp(1.375rem,2.4vw,1.875rem)] leading-[1.02] text-ink ${UNDERLINE}`}
        >
          {edition.headline}
        </h2>
      </Link>
    </aside>
  );
}
