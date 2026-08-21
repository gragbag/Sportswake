import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import {
  editionFromBrief,
  editionFromSlot,
  editionWindow,
  type Edition,
} from "../lib/edition";
import type { Brief, BriefSection } from "../types";
import { BriefMeta } from "./BriefMeta";
import { BriefPlate } from "./BriefPlate";
import { PressShell } from "./PressShell";
import { SlugRule, TARGET, UNDERLINE } from "./press";
import { Reader } from "./Reader";
import { SectionRow } from "./SectionRow";

/**
 * Break a headline into balanced typeset lines.
 *
 * The load sequence staggers the lead headline line by line, and there is no
 * way to read wrapped lines back out of the DOM without measuring after paint
 * and freezing the wrap. So the lines are decided here instead: greedily, by
 * character budget, rebalancing what is left against the slots remaining.
 */
function splitLines(text: string, count: number): string[] {
  const lines: string[] = [];
  let rest = text.split(" ");

  for (let slot = count; slot > 0 && rest.length > 0; slot -= 1) {
    if (slot === 1) {
      lines.push(rest.join(" "));
      break;
    }
    const budget = rest.join(" ").length / slot;
    const width = (n: number): number => rest.slice(0, n).join(" ").length;
    let take = 1;
    while (
      take < rest.length - slot + 1 &&
      Math.abs(width(take + 1) - budget) <= Math.abs(width(take) - budget)
    ) {
      take += 1;
    }
    lines.push(rest.slice(0, take).join(" "));
    rest = rest.slice(take);
  }

  return lines;
}

/**
 * The page before the briefs arrive.
 *
 * Outlines at the real aspect ratios and the real widths, so nothing moves
 * when the copy lands. No shimmer: a sweeping gradient says "wait" over and
 * over without ever saying how long, and it is the first thing to look cheap
 * on a page made of hairlines.
 */
function Skeleton() {
  return (
    <div className="pt-8">
      <div className="aspect-video w-full border border-rule" />
      <div className="mt-4 h-[11px] w-[20rem] max-w-full border border-rule" />
      <div className="mt-3 h-[clamp(2.75rem,7vw,5.5rem)] w-full border border-rule" />
      <div className="mt-12 grid grid-cols-1 gap-y-10 md:grid-cols-[repeat(2,46%)] md:justify-between md:gap-y-0">
        {[0, 1].map((i) => (
          <div key={i} className="flex gap-4 md:block">
            <div className="w-[46%] shrink-0 md:w-full">
              <div className="aspect-video w-full border border-rule" />
            </div>
            <div className="min-w-0 flex-1 md:pt-4">
              <div className="h-[11px] w-[12rem] max-w-full border border-rule" />
              <div className="mt-2 h-[clamp(1.375rem,2.4vw,1.875rem)] w-full border border-rule" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The brief, as a front page.
 *
 * The plates ARE the day: the edition you are reading is the front page, and
 * any other edition filed today sits under it the way back numbers sit on a
 * shelf -- a lead plate and up to two at 46% of it. That replaces the old
 * sidebar rail outright while still answering what it answered -- what else is
 * there today, and is it worth my time -- in the size and position of the
 * plates rather than in a list of rows.
 *
 * At the current cadence of one edition a day there are no back numbers, so
 * the page is the lead plate alone and the shelf below it renders nothing.
 * The layout is deliberately kept rather than cut down to match: which
 * editions publish is one line of briefs.yml, and this composition is what
 * makes turning a second one back on a config change instead of a rewrite.
 *
 * Clicking the lead opens it to read; clicking a back number brings it to the
 * front. Same component, and the meta line above each says which is which.
 */

const BRIEF_CACHE_KEY = "sportswake:brief";

/** The last bundle this browser saw, or null. Stale on purpose -- it paints
 *  instantly while the fresh fetch is in flight, like yesterday's paper on
 *  the table while today's is on the doorstep. */
function readCachedBrief(): Brief | null {
  try {
    const raw = localStorage.getItem(BRIEF_CACHE_KEY);
    return raw ? (JSON.parse(raw) as Brief) : null;
  } catch {
    return null; // private mode, or a corrupt entry: fall through to the fetch
  }
}

function saveCachedBrief(brief: Brief) {
  try {
    localStorage.setItem(BRIEF_CACHE_KEY, JSON.stringify(brief));
  } catch {
    /* private mode: caching is an optimisation, never a requirement */
  }
}

export function BriefPage() {
  const { session } = useAuth();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [filed, setFiled] = useState<Record<string, Brief>>({});
  const [reading, setReading] = useState<BriefSection | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Slots already fetched, so moving between editions is instant rather than a
  // spinner each time. The rest of the day is pulled in the background once the
  // one you asked for has landed.
  const cache = useRef(new Map<string, Brief>());

  const load = useCallback(async (want: string | null, background = false) => {
    const key = want ?? "__auto__";
    const hit = cache.current.get(key);
    if (hit) {
      if (!background) setBrief(hit);
      return hit;
    }
    const q = new URLSearchParams({ local_hour: String(new Date().getHours()) });
    if (want) q.set("slot", want);
    // The auto request asks for the whole day in one response; the sibling
    // editions land in the cache below, so the background loads that used to
    // fetch them become instant cache hits and never touch the network.
    else q.set("all_slots", "1");
    const res = await apiFetch(`/api/brief?${q}`);
    if (!res.ok) throw new Error(String(res.status));
    const data: Brief = await res.json();
    cache.current.set(key, data);
    // Only the day bundle is worth keeping across visits -- it carries every
    // edition, so the next visit paints whole before its first byte arrives.
    if (!want) saveCachedBrief(data);
    if (data.editions) {
      for (const [s, edition] of Object.entries(data.editions)) {
        cache.current.set(s, edition);
      }
      // Kept in state as well as in the ref: the archive plates upgrade from
      // slot summaries to real item counts as editions land, and a ref alone
      // would never re-render to show it.
      setFiled((prev) => ({ ...prev, ...data.editions }));
    } else if (data.slot) {
      cache.current.set(data.slot, data);
      setFiled((prev) => ({ ...prev, [data.slot as string]: data }));
    }
    if (!background) setBrief(data);
    return data;
  }, []);

  // First paint from the last visit's bundle, before any network at all.
  // Editions land in both caches so the plates render fully populated.
  useEffect(() => {
    const cached = readCachedBrief();
    if (!cached) return;
    setBrief((current) => current ?? cached);
    if (cached.editions) {
      for (const [s, edition] of Object.entries(cached.editions)) {
        cache.current.set(s, edition);
      }
      setFiled((prev) => ({ ...cached.editions, ...prev }));
    }
  }, []);

  useEffect(() => {
    // Deliberately NOT gated on auth restore: an anonymous reader should
    // never wait on a session that is not coming. A signed-in reader's
    // first response may be the anonymous brief; this effect re-runs when
    // the session lands and replaces it. The brief on screen -- cached or
    // anonymous -- stays up while the replacement is in flight, which is
    // what makes both handovers invisible.
    cache.current.clear();
    setError(null);

    load(null)
      .then((first) => {
        for (const s of first.available_slots) {
          if (s.slot !== first.slot) load(s.slot, true).catch(() => {});
        }
      })
      .catch(() => setError("Couldn’t load the brief. Check your connection."));
  }, [session, load]);

  // "Live" is the newest edition actually filed, not the one you are looking
  // at -- so opening a back number says EARLIER rather than relabelling itself
  // as current.
  const newest = useMemo(() => {
    const slots = brief?.available_slots ?? [];
    if (slots.length === 0) return null;
    return slots.reduce((best, s) =>
      Date.parse(s.generated_at) > Date.parse(best.generated_at) ? s : best,
    ).slot;
  }, [brief]);

  const editions = useMemo<Edition[]>(() => {
    if (!brief) return [];
    return brief.available_slots
      .map((s) => {
        // Newest AND actually current. The API sets is_stale when the served
        // slot is not today's, and calling an eleven-hour-old brief LIVE
        // because it happens to be the last one filed is the kind of small lie
        // that makes a reader stop trusting the rest of the page.
        const live = s.slot === newest && !brief.is_stale;
        const full = filed[s.slot];
        return (full && editionFromBrief(full, live)) || editionFromSlot(s, live);
      })
      .sort((a, b) => Date.parse(b.generatedAt) - Date.parse(a.generatedAt));
  }, [brief, filed, newest]);

  const windowMs = useMemo(
    () => editionWindow(brief?.available_slots ?? []),
    [brief],
  );

  const lead = editions.find((e) => e.slot === brief?.slot) ?? null;
  const back = editions.filter((e) => e.slot !== brief?.slot);
  const lines = useMemo(
    () => (lead?.headline ? splitLines(lead.headline, 3) : []),
    [lead?.headline],
  );

  const league = brief?.sections.find((s) => s.scope === "league") ?? null;
  const teams = useMemo(
    () => brief?.sections.filter((s) => s.scope === "team") ?? [],
    [brief],
  );

  function go(next: string) {
    if (!brief || next === brief.slot) return;
    load(next).catch(() => setError("Couldn’t load that edition."));
  }

  if (error) {
    return (
      <PressShell>
        <h1 className="t-display max-w-[20ch] pt-8 text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          The wire is down.
        </h1>
        <p className="t-read max-w-[46ch] pt-4 text-ink-mute">{error}</p>
      </PressShell>
    );
  }

  if (!brief) {
    return (
      <PressShell>
        <Skeleton />
      </PressShell>
    );
  }

  if (!brief.slot || !league || !lead) {
    return (
      <PressShell>
        <h1 className="t-display max-w-[20ch] pt-8 text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          No brief yet.
        </h1>
        <p className="t-read max-w-[46ch] pt-4 text-ink-mute">
          The first edition appears here once the day’s coverage has been
          gathered.
        </p>
      </PressShell>
    );
  }

  return (
    <PressShell generatedAt={lead.generatedAt} stale={brief.is_stale}>
      {/* Keyed on the slot: switching editions remounts the subtree, so the
            load sequence replays and IS the transition. A wrapper fade on top
            of it would be a second opinion about the same movement. */}
      <div key={brief.slot}>
        <article className="group pt-8">
          <div className="relative">
            <BriefPlate edition={lead} variant="lead" windowMs={windowMs} />
            <div className="pt-4">
              <BriefMeta edition={lead} id="lead-meta" />
            </div>
            <h1
              id="lead-head"
              className={`t-display pt-3 text-[clamp(2.75rem,7vw,5.5rem)] leading-[0.92] ${UNDERLINE}`}
            >
              {lines.map((line, i) => (
                <span
                  key={line}
                  className="anim-line block"
                  style={{ "--i": i } as CSSProperties}
                >
                  {/* The trailing space keeps the accessible name reading as
                        a sentence; it collapses at the end of a line. */}
                  {line}{" "}
                </span>
              ))}
            </h1>
            <button
              type="button"
              onClick={() => setReading(league)}
              aria-labelledby="lead-meta lead-head"
              className={TARGET}
            />
          </div>
          {lead.standfirst && (
            <p className="t-read max-w-[62ch] pt-4 text-ink-mute">
              {lead.standfirst}
            </p>
          )}
        </article>

        {back.length > 0 && (
          <section aria-label="Other editions today" className="pt-12 md:pt-16">
            <SlugRule label="Also today" count={back.length} />

            {/* Two 46% columns with the remaining 8% as the gutter, so the
                  hierarchy holds by construction rather than by arithmetic on a
                  gap. Below md they stack, but each becomes a plate-left digest
                  row -- a full-width back number would be 100% of the lead and
                  the hierarchy would collapse exactly where the screen can
                  least afford it. */}
            <div className="grid grid-cols-1 gap-y-10 pt-6 md:grid-cols-[repeat(2,46%)] md:justify-between md:gap-y-0">
              {back.map((edition) => (
                <article key={edition.slot} className="group relative">
                  <div className="flex gap-4 md:block">
                    <div className="w-[46%] shrink-0 md:w-full">
                      <BriefPlate
                        edition={edition}
                        variant="archive"
                        windowMs={windowMs}
                      />
                    </div>
                    <div className="min-w-0 flex-1 md:pt-4">
                      <BriefMeta
                        edition={edition}
                        id={`${edition.slot}-meta`}
                      />
                      <h2
                        id={`${edition.slot}-head`}
                        className={`t-display pt-2 text-[clamp(1.375rem,2.4vw,1.875rem)] leading-[1.02] ${UNDERLINE}`}
                      >
                        {edition.headline}
                      </h2>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => go(edition.slot)}
                    aria-labelledby={`${edition.slot}-meta ${edition.slot}-head`}
                    className={TARGET}
                  />
                </article>
              ))}
            </div>
          </section>
        )}

        <section aria-label="Your teams" className="pt-12 md:pt-16">
          <SlugRule
            label="Your teams"
            count={teams.length > 0 ? teams.length : undefined}
          />

          {teams.length > 0 ? (
            <>
              <ul className="mt-1">
                {teams.map((section) => (
                  <SectionRow
                    key={section.team}
                    section={section}
                    onOpen={() => setReading(section)}
                  />
                ))}
              </ul>
              {brief.omitted_team_count > 0 && (
                <p className="t-wire mt-4 text-ink-mute">
                  {brief.omitted_team_count} followed team
                  {brief.omitted_team_count === 1 ? "" : "s"} had nothing beyond
                  what you’ve already read.
                </p>
              )}
            </>
          ) : (
            <div className="border-t border-rule pt-6">
              <p className="t-read max-w-[46ch] text-ink-mute">
                {session
                  ? "Follow teams and their news files under the league brief."
                  : "Create an account to follow teams and get their news too."}
              </p>
              <Link
                to={session ? "/settings" : "/signup"}
                className="t-wire mt-4 inline-block border-b border-spot pb-1 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
              >
                {session ? "Choose teams" : "Get started"}
              </Link>
            </div>
          )}
        </section>
      </div>

      {/* Fixed and full-screen, so it sits inside the column in the markup and
          over the whole page on screen. */}
      {reading && (
        <Reader
          section={reading}
          slot={brief.slot}
          generatedAt={lead.generatedAt}
          onClose={() => setReading(null)}
        />
      )}
    </PressShell>
  );
}
