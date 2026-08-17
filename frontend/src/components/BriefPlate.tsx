import type { Edition } from "../lib/edition";
import { FreshnessRule } from "./FreshnessRule";

/**
 * The cover, composed as a press plate rather than a photo well.
 *
 * There is no image to show, so the plate is built the way a two-colour page
 * is built: the wash pass goes down first -- the filing hour, huge, bled off
 * the left and bottom edges so it crops at the trim -- and the black pass
 * overprints it. Registration marks straddle the trim corners because that is
 * what makes the two passes line up. None of it is ornament; it is the
 * mechanics of the thing, drawn at full size.
 *
 * The numeral is the hour the edition was filed. Three plates reading 06, 12
 * and 21 across the page say "three times a day" without a line of copy, and
 * unlike an invented issue number it is a fact the API already knows.
 *
 * The numeral and the overprinted slug are both aria-hidden: the hour is
 * restated in the meta line's dateline and the headline is the <h1> itself. A
 * screen reader should hear the edition once.
 */
export function BriefPlate({
  edition,
  variant,
  windowMs,
}: {
  edition: Edition;
  variant: "lead" | "archive";
  windowMs: number;
}) {
  const lead = variant === "lead";
  const pad = lead
    ? "inset-x-[26px] bottom-[26px]"
    : "inset-x-[18px] bottom-[18px]";

  return (
    <div className="plate">
      {/* The frame goes spot on hover and focus -- a proof being marked up in
          the second colour. Nothing moves, nothing lifts. */}
      <span
        aria-hidden="true"
        className="plate-frame anim-rule group-hover:border-spot group-has-[:focus-visible]:border-spot"
      />

      <span aria-hidden="true" className="plate-numeral">
        {edition.hour}
      </span>

      <span aria-hidden="true" className="reg-mark reg-mark-tr" />
      <span aria-hidden="true" className="reg-mark reg-mark-br" />

      {/* The nameplate, printed over the wash.
          This carried the headline in an earlier pass and it was the weakest
          thing on the page: the same sentence set twice, once here and again
          as the <h1> six lines below, which reads as a duplication bug rather
          than as a plate. A plate identifies its edition -- that is the whole
          job of the furniture at the top of one -- so it says which of the
          day's three runs this is, and the news is left to be news once. */}
      <p
        aria-hidden="true"
        className="t-display plate-slug absolute top-[26px] left-[26px] text-ink"
      >
        {edition.label}
      </p>

      {/* What is in this edition, opposite the nameplate.
          A 16:9 plate at full column width is 600px tall, and a nameplate and
          an hour do not fill it -- the lead plate was two-thirds empty without
          this. A contents block is what a front page actually puts in that
          space, and it is the most useful thing the plate can say: not just
          which edition this is, but whether it is worth opening. Suppressed
          below md, where a 46%-width plate has no room for it. */}
      {lead && edition.stories.length > 0 && (
        <div className="absolute top-[26px] right-[26px] hidden w-[38%] md:block">
          <p className="t-wire pb-3 text-ink-mute">In this edition</p>
          <ul>
            {edition.stories.map((headline) => (
              <li key={headline} className="border-t border-rule py-2.5">
                <p className="t-read text-[0.9375rem] leading-[1.35] text-ink">
                  {headline}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className={`absolute ${pad}`}>
        {lead && edition.live ? (
          <>
            <FreshnessRule
              generatedAt={edition.generatedAt}
              windowMs={windowMs}
            />
            {edition.teams.length > 0 && (
              <p className="t-wire pt-3 text-ink-mute">
                {edition.teams.map((team, i) => (
                  <span key={team}>
                    {i > 0 && <span aria-hidden="true"> · </span>}
                    {team}
                  </span>
                ))}
              </p>
            )}
          </>
        ) : (
          // Superseded editions get the same rule position, drawn full width
          // and inert. The shape stays so the live edition's partial rule reads
          // as a measurement against it.
          <span aria-hidden="true" className="anim-rule block h-px bg-rule" />
        )}
      </div>
    </div>
  );
}
