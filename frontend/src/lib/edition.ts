import type { Brief, BriefSlot } from "../types";
import { formatHour } from "./dateline";

/**
 * One filed edition, as the plate needs it.
 *
 * The API talks in slots and sections; the page talks in editions. This is the
 * seam between them, kept in one place so the components never have to know
 * that `itemCount` is a set union over sections or that the headline is really
 * the first sentence of generated prose.
 */
export type Edition = {
  slot: string;
  label: string;
  generatedAt: string;
  /** The plate numeral: the hour it was filed. */
  hour: string;
  headline: string;
  standfirst: string;
  /** Null when only the slot summary is known and the full brief has not landed. */
  itemCount: number | null;
  readMinutes: number;
  /** Team codes covered, for the topics row. */
  teams: string[];
  /** Top story headlines, for the plate's contents block. */
  stories: string[];
  live: boolean;
};

export const SLOT_LABEL: Record<string, string> = {
  morning: "Morning",
  midday: "Midday",
  night: "Night",
};

/** Roughly how long this takes to read, at ~230 words a minute. */
export function minutes(words: number): number {
  return Math.max(1, Math.round(words / 230));
}

/**
 * Generated prose down to plain text.
 *
 * The body is markdown, but only the subset `Prose` renders -- paragraphs and
 * inline emphasis -- so stripping it is a matter of dropping asterisks rather
 * than parsing anything.
 */
function plain(md: string): string {
  return md.replace(/\*+/g, "").replace(/\s+/g, " ").trim();
}

const HEAD_MAX = 58;

/* The two trims that decide where the headline stops. Named, because they run
   in two places now -- once inside the truncation branch, before the carry is
   measured, and once on a headline short enough never to have been cut. */
const TRAILING_PUNCT = /[\s,;:.—-]+$/;
const DANGLING =
  /\s+(of|to|a|an|the|and|or|in|on|at|by|for|with|from|as|that|into|over|after|before|than)$/i;

/**
 * Split the opening of a brief into a headline and the line under it.
 *
 * The sections are generated prose and carry no headline of their own, so the
 * head has to be cut from the first sentence. The cut is made at a clause
 * boundary wherever one is in reach, because a headline that stops at a comma
 * still reads as a headline -- where one chopped mid-phrase and handed an
 * ellipsis ("...never gave it back,…") reads as a bug, and reads as one at
 * 5.5rem across the top of the page.
 *
 * Whatever was cut off is not thrown away; it becomes the front of the
 * standfirst, so the deck continues the sentence the head started.
 */
export function splitLead(md: string): { headline: string; standfirst: string } {
  const text = plain(md);
  if (!text) return { headline: "", standfirst: "" };

  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)/g)?.map((s) => s.trim()) ?? [
    text,
  ];

  let headline = sentences[0] ?? text;
  let rest = sentences.slice(1).join(" ").trim();

  if (headline.length > HEAD_MAX) {
    // Look a little past the limit for a clause boundary before falling back
    // to the last whole word.
    const reach = headline.slice(0, HEAD_MAX + 14);
    const clause = Math.max(
      reach.lastIndexOf(", "),
      reach.lastIndexOf("; "),
      reach.lastIndexOf(" — "),
    );
    const cut = clause > 24 ? clause : reach.lastIndexOf(" ", HEAD_MAX);
    // Trim the head to its FINAL printed form before measuring what carries
    // down, so that whatever the trims remove lands in the standfirst instead
    // of falling between the two halves. Trimming afterwards deleted the word
    // outright: "...saw movement in Atlanta and Orlando on Tuesday" cut to
    // "...saw movement in Atlanta" over "Orlando on Tuesday." and the reader
    // was left to notice the missing "and" at 5.5rem.
    const keep = headline
      .slice(0, cut > 0 ? cut : HEAD_MAX)
      .trim()
      .replace(TRAILING_PUNCT, "")
      .replace(DANGLING, "");
    const carried = headline.slice(keep.length).replace(/^[\s,;:—-]+/, "");
    rest = `${carried} ${rest}`.trim();
    headline = keep;
  }

  // A headline is not a sentence; the punctuation is the prose's, not ours.
  // Never end on a dangling function word either: cutting the real "...have
  // been sold to a partnership of Bob Iger and Josh Kushner" at the character
  // limit leaves "...sold to a partnership of", which reads as a truncation
  // bug even though nothing was elided. Both are no-ops on a head that came
  // through the branch above -- they already ran there, where the carry could
  // still catch what they took.
  headline = headline.replace(TRAILING_PUNCT, "").replace(DANGLING, "");

  if (rest) rest = rest.charAt(0).toUpperCase() + rest.slice(1);
  if (rest.length > 150) {
    // Stop at a full stop if one is in range: a standfirst that ends on a
    // finished thought beats one that trails off mid-clause into an ellipsis.
    const window = rest.slice(0, 150);
    const stop = Math.max(
      window.lastIndexOf(". "),
      window.lastIndexOf("? "),
      window.lastIndexOf("! "),
    );
    rest =
      stop > 60
        ? window.slice(0, stop + 1)
        : `${window.slice(0, window.lastIndexOf(" "))}…`;
  }

  return { headline, standfirst: rest };
}

/** An edition built from the full brief, once it has been fetched. */
export function editionFromBrief(brief: Brief, live: boolean): Edition | null {
  if (!brief.slot || !brief.generated_at) return null;

  const league = brief.sections.find((s) => s.scope === "league");
  const lead = splitLead(league?.body_md ?? "");

  const stories = new Set(
    brief.sections.flatMap((s) => s.stories.map((story) => story.id)),
  );
  const words = brief.sections.reduce((sum, s) => sum + s.word_count, 0);

  return {
    slot: brief.slot,
    label: SLOT_LABEL[brief.slot] ?? brief.slot,
    generatedAt: brief.generated_at,
    hour: formatHour(brief.generated_at),
    headline: lead.headline,
    standfirst: lead.standfirst,
    itemCount: stories.size,
    readMinutes: minutes(words),
    teams: brief.sections
      .filter((s) => s.scope === "team" && s.team)
      .map((s) => s.team as string)
      .slice(0, 3),
    // In the order the section used them, so the plate matches the prose.
    stories: (league?.stories ?? []).map((s) => s.headline).slice(0, 3),
    live,
  };
}

/**
 * An edition built from the slot summary alone.
 *
 * The archive plates render from this the moment the first response lands, so
 * the page composes immediately and then fills in item counts as the other
 * slots arrive in the background -- rather than holding three empty frames
 * until every fetch has finished.
 */
export function editionFromSlot(slot: BriefSlot, live: boolean): Edition {
  return {
    slot: slot.slot,
    label: SLOT_LABEL[slot.slot] ?? slot.slot,
    generatedAt: slot.generated_at,
    hour: formatHour(slot.generated_at),
    headline: splitLead(slot.first_line).headline,
    standfirst: "",
    itemCount: null,
    readMinutes: minutes(slot.word_count),
    teams: [],
    stories: [],
    live,
  };
}

/**
 * The watch to assume when the day has filed only one edition to measure.
 *
 * A day, not eight hours. At one edition a day this is not a fallback at all
 * -- it is the value the rule always runs on, because two filings are what
 * `editionWindow` needs to measure a real gap and there is only ever one. At
 * eight hours the day's only edition drained to "Standing" by mid-afternoon
 * with nothing published to supersede it, which is the rule reporting a
 * supersession that did not happen.
 */
const NOMINAL_WINDOW_MS = 24 * 3_600_000;

/**
 * How long the live edition stands before the next one is due.
 *
 * Measured from the gap between the last two editions actually filed today,
 * so the rule tracks the cadence instead of asserting one. That matters
 * because the cadence is an editorial decision living in a single line of
 * briefs.yml, not a constant: at one edition a day the measurement never has
 * two filings to work from and the nominal day below carries it, and if a
 * second slot is switched back on the gap starts measuring itself again
 * without anything here changing.
 */
export function editionWindow(slots: BriefSlot[]): number {
  const filed = slots
    .map((s) => Date.parse(s.generated_at))
    .filter((t) => Number.isFinite(t))
    .sort((a, b) => a - b);

  if (filed.length < 2) return NOMINAL_WINDOW_MS;
  return Math.max(filed[filed.length - 1] - filed[filed.length - 2], 3_600_000);
}
