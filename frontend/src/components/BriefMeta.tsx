import { formatDayStamp } from "../lib/dateline";
import type { Edition } from "../lib/edition";

/**
 * The slug line: standing, edition, extent.
 *
 * It sits ABOVE the headline, not below it, because on a printed take the slug
 * is what you read first to decide whether the story is for you -- and here it
 * carries the fact that matters most, which of the day's three editions you
 * are looking at.
 *
 * LIVE is a 7px spot square, not a circle: registration-mark logic rather than
 * notification-badge logic. Superseded editions say EARLIER in words and are
 * never dimmed -- an edition you have already read is not less legible than
 * the current one, and this page is as much an archive as a front page.
 */
export function BriefMeta({ edition, id }: { edition: Edition; id?: string }) {
  return (
    <p
      id={id}
      className="t-wire flex flex-wrap items-center gap-x-2 gap-y-1 text-ink-mute"
    >
      {edition.live && (
        <span aria-hidden="true" className="inline-block size-[7px] bg-spot" />
      )}
      {/* LIVE carries full ink weight; EARLIER stays muted. The spot ink is
          spent on the square alone -- the accent budget is three places on this
          page and this line is only entitled to one of them. */}
      <span className={edition.live ? "text-ink" : undefined}>
        {edition.live ? "Live" : "Earlier"}
      </span>
      <span aria-hidden="true">·</span>
      <span>{edition.label}</span>
      <span aria-hidden="true">·</span>
      <time dateTime={edition.generatedAt}>
        {formatDayStamp(edition.generatedAt)}
      </time>
      {edition.itemCount !== null && (
        <>
          <span aria-hidden="true">·</span>
          <span>
            {edition.itemCount} item{edition.itemCount === 1 ? "" : "s"}
          </span>
        </>
      )}
      <span aria-hidden="true">·</span>
      <span>{edition.readMinutes} min</span>
    </p>
  );
}
