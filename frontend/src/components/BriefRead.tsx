import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { apiFetch } from "../lib/auth";
import { formatClock, formatDayStamp } from "../lib/dateline";
import { SLOT_LABEL, minutes } from "../lib/edition";
import { Prose } from "../lib/prose";
import type { Brief, BriefSection } from "../types";
import { PressShell } from "./PressShell";
import { SlugRule } from "./press";

/**
 * One section of a brief, as a page.
 *
 * This was a sheet over the front page, on the reasoning that reading a
 * section is a detour rather than a destination. That reasoning holds for a
 * two-hundred-word team file and it is plainly wrong for the league brief,
 * which runs nine hundred words and is the thing the entire front page exists
 * to deliver you to. Putting the paper's body copy in a modal says it is a
 * peek at something small, and it read that way: the headline you clicked
 * vanished, the text opened with no title and no entry, and the page behind
 * showed through cropped mid-word.
 *
 * As a route it also gets a URL, which a news product needs -- the one page
 * worth sending to somebody was the one page that could not be linked.
 *
 * The title is the edition, not the headline. The headline is cut from the
 * first sentence of this very text, so printing it above the body sets the
 * same words twice and reads as a stutter. A section front names the section
 * and lets the story start.
 */
export function BriefRead() {
  const { slot, team } = useParams();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBrief(null);
    setError(null);
    apiFetch(`/api/brief?slot=${encodeURIComponent(slot ?? "")}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: Brief) => alive && setBrief(data))
      .catch(() => alive && setError("Couldn’t load that edition."));
    return () => {
      alive = false;
    };
  }, [slot]);

  const back = (
    <Link
      to="/"
      className="t-wire inline-block pt-8 text-ink-mute hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
    >
      ← The brief
    </Link>
  );

  if (error || (brief && !brief.slot)) {
    return (
      <PressShell>
        {back}
        <h1 className="t-display max-w-[20ch] pt-8 text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          No such edition.
        </h1>
        {error && <p className="t-read max-w-[46ch] pt-4 text-ink-mute">{error}</p>}
      </PressShell>
    );
  }

  if (!brief) {
    return (
      <PressShell>
        {back}
        <p className="t-wire pt-8 text-ink-mute">Loading…</p>
      </PressShell>
    );
  }

  // The API answers an unknown slot with the newest edition rather than a 404,
  // which is the right call for the API and leaves the URL lying: /brief/nosuch
  // rendered the night brief under a name that was not its own. Canonicalise,
  // so a link always shows what it says it will.
  if (brief.slot && slot !== brief.slot) {
    return (
      <Navigate
        to={team ? `/brief/${brief.slot}/${team}` : `/brief/${brief.slot}`}
        replace
      />
    );
  }

  const section: BriefSection | undefined = team
    ? brief.sections.find((s) => s.team === team)
    : brief.sections.find((s) => s.scope === "league");

  if (!section) {
    return (
      <PressShell generatedAt={brief.generated_at ?? null}>
        {back}
        <h1 className="t-display max-w-[24ch] pt-8 text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          Nothing filed under that.
        </h1>
      </PressShell>
    );
  }

  const isLeague = section.scope === "league";
  const label = SLOT_LABEL[brief.slot as string] ?? brief.slot;
  // "Night brief", matching the plate's nameplate and the house's sentence
  // case. "The Night brief" put a capital and a lowercase word side by side
  // and read as a typo at 4.5rem.
  const title = isLeague ? `${label} brief` : (section.team_name ?? "Brief");
  const filed = brief.generated_at ?? null;

  return (
    <PressShell generatedAt={filed} stale={brief.is_stale}>
      {back}

      <article className="pt-8">
        {/* The slug line, above the title, the way the front page sets it. */}
        <p className="t-wire flex flex-wrap items-center gap-x-2 gap-y-1 text-ink-mute">
          {!isLeague && section.team && (
            <>
              <span className="text-ink">{section.team}</span>
              <span aria-hidden="true">·</span>
            </>
          )}
          <span>{label}</span>
          {filed && (
            <>
              <span aria-hidden="true">·</span>
              <time dateTime={filed}>{formatDayStamp(filed)}</time>
              <span aria-hidden="true">·</span>
              <span>{formatClock(filed)}</span>
            </>
          )}
          <span aria-hidden="true">·</span>
          <span>{section.word_count} words</span>
          <span aria-hidden="true">·</span>
          <span>{minutes(section.word_count)} min</span>
        </p>

        <h1 className="t-display max-w-[18ch] pt-3 text-[clamp(2.25rem,6vw,4.5rem)] leading-[0.94]">
          {title}
        </h1>

        {/* The measure is the whole point of a reading page: 66 characters,
            set on the paper rather than inside a panel floating over it. The
            drop cap is the opening a piece of writing is entitled to and the
            single thing the old sheet most obviously lacked. */}
        <div className="prose-wire prose-open max-w-[66ch] pt-10 text-ink">
          <Prose text={section.body_md} />
        </div>
      </article>

      {section.stories.length > 0 && (
        <section className="max-w-[66ch] pt-12 md:pt-16">
          <SlugRule label="Sources" count={section.stories.length} />

          {/* The brief summarises and points, and the pointing is part of the
              piece -- never collapsed. The headline goes to OUR coverage page,
              which is the claim this product exists to make; the outlet that
              broke it is the external link one step down. */}
          <ul className="pt-2">
            {section.stories.map((story) => (
              <li key={story.id} className="group border-t border-rule">
                <Link
                  to={`/story/${story.id}`}
                  className="block pt-4 pb-1 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-spot"
                >
                  <p className="t-read text-ink decoration-1 underline-offset-4 group-hover:underline">
                    {story.headline}
                  </p>
                </Link>
                <p className="t-wire pb-4 text-ink-mute">
                  {story.outlet_count}{" "}
                  {story.outlet_count === 1 ? "outlet" : "outlets"}
                  <span aria-hidden="true"> · </span>
                  <a
                    href={story.lead_url}
                    target="_blank"
                    rel="noreferrer"
                    title={story.outlets.join(", ")}
                    className="hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
                  >
                    {story.lead_outlet} first ↗
                  </a>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </PressShell>
  );
}
