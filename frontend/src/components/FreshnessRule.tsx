import { useState } from "react";
import { hoursSince } from "../lib/dateline";

/**
 * How much of this edition's watch is left.
 *
 * A 2px spot rule whose width is the time remaining before the next edition is
 * due: full at filing, gone when the next one lands. It is the one mark on the
 * page that measures something real rather than decorating, which is why it
 * carries no percentage readout -- a number would turn it into a progress bar,
 * and an edition is not a task completing.
 *
 * The window is passed in rather than fixed here because the cadence is an
 * editorial decision, not a property of this component: it is a day while the
 * product files once a day, and becomes the measured gap between filings the
 * moment a second edition is switched back on. Hardcoding either number would
 * make this rule start lying on the deploy that changed that line.
 *
 * Read once, at mount. No interval: a brief does not get fresher while you
 * look at it, and a rule creeping leftward would imply it might.
 */
export function FreshnessRule({
  generatedAt,
  windowMs,
}: {
  generatedAt: string;
  windowMs: number;
}) {
  const [{ remaining, hours }] = useState(() => {
    const now = Date.now();
    return {
      remaining: Math.min(
        1,
        Math.max(0, 1 - (now - Date.parse(generatedAt)) / windowMs),
      ),
      hours: hoursSince(generatedAt, now),
    };
  });

  return (
    <div>
      <p className="t-wire pb-2 text-ink-mute">
        {remaining > 0 ? "Fresh" : "Standing"}
        <span aria-hidden="true"> · </span>
        {hours}h ago
      </p>
      {/* The track is the paper itself -- only the inked portion is drawn. */}
      <div
        aria-hidden="true"
        className="anim-rule h-0.5 bg-spot"
        style={{ width: `${remaining * 100}%` }}
      />
    </div>
  );
}
