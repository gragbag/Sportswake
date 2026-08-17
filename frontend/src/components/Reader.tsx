import { useEffect, useRef } from "react";
import { formatClock } from "../lib/dateline";
import { SLOT_LABEL, minutes } from "../lib/edition";
import { Prose } from "../lib/prose";
import type { BriefSection } from "../types";

/**
 * The full text of one section, as a sheet.
 *
 * A sheet rather than a route, because reading a section is a detour and not a
 * destination: you come back to the same list, in the same place, every time,
 * and a route would push history for what is really an expand.
 *
 * Set as a page pulled off the run -- paper-lift ground, hairline rules, no
 * radius and no shadow. It separates from the page behind it by tone and by
 * the veil alone, which is the same argument the plates make. The veil is a
 * flat wash rather than a blur: a frosted panel over newsprint would undo the
 * one rule this whole design keeps.
 *
 * Sources sit at the bottom and are never collapsed -- the brief summarises
 * and points, and the pointing is part of the piece.
 */
export function Reader({
  section,
  slot,
  generatedAt,
  onClose,
}: {
  section: BriefSection;
  slot: string;
  generatedAt?: string;
  onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // The page behind must not scroll under the sheet -- on a phone that reads
    // as the app losing your place.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  const isLeague = section.scope === "league";
  const title = isLeague
    ? `${SLOT_LABEL[slot] ?? slot} brief`
    : (section.team_name ?? "Brief");

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto overscroll-contain sm:p-6">
      <div aria-hidden="true" className="anim-veil fixed inset-0 bg-veil" />
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="fixed inset-0 cursor-default"
      />

      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative z-10 h-fit min-h-full w-full max-w-[42rem] border-x border-rule bg-paper-lift pb-24 outline-none sm:min-h-0 sm:border"
      >
        {/* Sticky header, so the way out never scrolls away. Solid, not
            translucent: this is the top of a sheet, not glass over it. */}
        <div className="sticky top-0 z-10 flex items-baseline gap-4 border-b border-rule bg-paper-lift px-5 py-4 sm:px-8">
          {!isLeague && section.team && (
            <span className="t-wire shrink-0 text-ink-mute">{section.team}</span>
          )}
          <div className="min-w-0 flex-1">
            <p className="t-display text-[1.125rem] text-ink">{title}</p>
            <p className="t-wire mt-1.5 text-ink-mute">
              {generatedAt && (
                <>
                  <time dateTime={generatedAt}>{formatClock(generatedAt)}</time>
                  <span aria-hidden="true"> · </span>
                </>
              )}
              {section.word_count} words
              <span aria-hidden="true"> · </span>
              {minutes(section.word_count)} min
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="t-wire shrink-0 cursor-pointer text-ink-mute hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
          >
            Close
          </button>
        </div>

        <div className="px-5 pt-8 sm:px-8">
          <div className="prose-wire text-ink">
            <Prose text={section.body_md} />
          </div>

          {section.stories.length > 0 && (
            <div className="mt-12">
              <div className="flex items-baseline gap-4">
                <p className="t-wire text-ink">Sources</p>
                <span aria-hidden="true" className="h-px flex-1 bg-rule" />
                <p className="t-wire text-ink-mute">{section.stories.length}</p>
              </div>

              <ul className="mt-1">
                {section.stories.map((story) => (
                  <li key={story.id} className="group border-t border-rule">
                    <a
                      href={story.lead_url}
                      target="_blank"
                      rel="noreferrer"
                      className="block py-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-spot"
                    >
                      <p className="t-read text-ink decoration-1 underline-offset-4 group-hover:underline">
                        {story.headline}
                      </p>
                      {/* Corroboration is the signal worth surfacing: one
                          outlet and sixteen are different claims about how real
                          a story is. */}
                      <p className="t-wire mt-2 text-ink-mute">
                        {story.outlet_count}{" "}
                        {story.outlet_count === 1 ? "outlet" : "outlets"}
                        <span aria-hidden="true"> · </span>
                        <span title={story.outlets.join(", ")}>
                          {story.lead_outlet} first
                        </span>
                      </p>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
