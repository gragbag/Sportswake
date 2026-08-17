/**
 * Dateline formatting, in the register a wire service uses.
 *
 * Times are the reader's own, not the newsroom's. An earlier draft stamped
 * everything PT because the design called for a single publication clock, but
 * the product already shows local times everywhere else and a brief filed at
 * "06:00 PT" is meaningless to someone reading it at 09:00 in Chicago.
 */

const DAY = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  day: "2-digit",
  month: "short",
});

const CLOCK = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const HOUR = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  hourCycle: "h23",
});

/** `MON 17 AUG`, from a full ISO instant. */
export function formatDayStamp(iso: string): string {
  const parts = DAY.formatToParts(new Date(iso));
  const part = (type: string): string =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${part("weekday")} ${part("day")} ${part("month")}`.toUpperCase();
}

/**
 * `MON 17 AUG`, from a bare `YYYY-MM-DD` slot date.
 *
 * Anchored at noon so the calendar day survives any timezone offset -- parsing
 * a bare date as UTC midnight lands on the previous day for every reader west
 * of Greenwich.
 */
export function formatDateStamp(slotDate: string): string {
  return formatDayStamp(new Date(`${slotDate}T12:00:00`).toISOString());
}

/** `06:00` */
export function formatClock(iso: string): string {
  return CLOCK.format(new Date(iso));
}

/** `06` -- the two-digit filing hour, used as the plate numeral. */
export function formatHour(iso: string): string {
  return HOUR.format(new Date(iso)).padStart(2, "0").slice(0, 2);
}

/** Whole hours elapsed since publication, floored at zero. */
export function hoursSince(iso: string, now: number): number {
  return Math.max(0, Math.floor((now - Date.parse(iso)) / 3_600_000));
}
