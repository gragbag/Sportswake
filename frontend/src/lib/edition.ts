import type { Brief, BriefSlot, BriefStory } from "../types";
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
  /** Every story in the edition, for the plate's composition marks. */
  items: BriefStory[];
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

/**
 * Drop the section headings a composed brief is built from.
 *
 * The brief is written as passages under "## Trades", "## Injuries" and so on.
 * Everything that reads the body as prose -- the front-page headline above
 * all -- has to skip those, or the headline set at 5.5rem across the top of
 * the paper becomes the word "Trades".
 */
function withoutHeadings(md: string): string {
  return md
    .split("\n")
    .filter((line) => !/^\s*#{1,6}\s/.test(line))
    .join("\n");
}

const HEAD_MAX = 58;

/* The two trims that decide where the headline stops. Named, because they run
   in two places now -- once inside the truncation branch, before the carry is
   measured, and once on a headline short enough never to have been cut. */
const TRAILING_PUNCT = /[\s,;:.—-]+$/;
const DANGLING =
  /\s+(of|to|a|an|the|and|or|in|on|at|by|for|with|from|as|that|into|over|after|before|than)$/i;

/**
 * The opening sentence of a body, allowing for abbreviations.
 *
 * A bare first-sentence regex cuts "The Oct. 30 game will open the
 * tournament's group stage" after "Oct." -- which produced the headline
 * "The Oct" and a standfirst starting "30 game will open". So a candidate
 * that is implausibly short, or that ends on something shaped like an
 * abbreviation, keeps reading.
 *
 * This runs for the front page and the reading page both, and on the reading
 * page it also decides what is REMOVED from the body: a bad split there would
 * leave the article opening mid-phrase, which is worse than a bad headline.
 */
const SENTENCE = /[^.!?]+[.!?]+(?:\s|$)/g;
const ABBREV = /\b(?:[A-Z][a-z]{0,3}|No|Mr|Mrs|Ms|Dr|St|vs)\.\s*$/;

function firstSentence(text: string): string {
  SENTENCE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = SENTENCE.exec(text)) !== null) {
    // Sliced from 0 rather than accumulated from match[0], because the match
    // is NOT necessarily a prefix: the pattern requires whitespace after the
    // stop, so it steps straight over "$12.5 billion" and starts matching at
    // "5 billion...". Concatenating those matches built a string that was
    // never in the text, and every offset taken from its length landed
    // mid-word -- bodies opened on "cord by a wide margin."
    const candidate = text.slice(0, match.index + match[0].length);
    if (!ABBREV.test(candidate)) return candidate;
  }
  return "";
}

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
  const text = plain(withoutHeadings(md));
  if (!text) return { headline: "", standfirst: "" };

  const opening = firstSentence(text);
  let headline = (opening || text).trim();
  let rest = text.slice(opening.length).trim();

  if (headline.length > HEAD_MAX) {
    // Look a little past the limit for a clause boundary before falling back
    // to the last whole word.
    //
    // The mark is searched for inside `reach` but the character AFTER it is
    // read from the full headline, which is the whole point: lastIndexOf(", ")
    // needs both characters inside the window, so a comma landing exactly on
    // the last index of `reach` could never be found and the cut fell back to
    // a word boundary. That is not a rare alignment -- it is what produced
    // "The NBA landscape has undergone significant structural" on the front
    // page, where the real clause ended four words later at "...this week,".
    const reach = headline.slice(0, HEAD_MAX + 14);
    const clauseAt = (mark: string): number => {
      for (let i = reach.length - 1; i >= 0; i -= 1) {
        // Requiring a following space is what keeps "$12.5", "2026-27" and
        // "17.8 percent" from reading as clause boundaries.
        if (reach[i] === mark && headline[i + 1] === " ") return i;
      }
      return -1;
    };
    const clause = Math.max(clauseAt(","), clauseAt(";"), clauseAt("—"));
    // With no clause boundary to cut at, take the last whole word in REACH
    // rather than the last one before HEAD_MAX. Stopping at 58 lands in the
    // middle of a noun phrase about as often as not -- "The Cleveland
    // Cavaliers have finalized a complex" is a headline that has clearly been
    // cut, where the same sentence to the edge of the window reads as one
    // somebody wrote: "...a complex multi-team transaction". The trims below
    // still catch a trailing function word either way.
    const cut = clause > 24 ? clause : reach.lastIndexOf(" ");
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

/**
 * A brief section as an article: headline, deck, and the body under them.
 *
 * The reading page used to title itself "Night brief", which names the section
 * rather than saying anything, and the front page's headline -- the one the
 * reader just clicked -- was thrown away on arrival.
 *
 * It is set as a real article instead. The catch is that the headline is cut
 * FROM this text, so printing both sets the same words twice; the opening
 * sentence is therefore lifted out of the body rather than repeated. Headline
 * plus deck reconstitute it exactly, which is the arrangement a newspaper
 * already uses: the head is a condensation, the deck carries the rest of the
 * thought, and the story starts at the second sentence.
 */
export function splitArticle(md: string): {
  headline: string;
  deck: string;
  body: string;
} {
  const paragraphs = md.split(/\n\s*\n/);
  // The head is cut from the first PROSE paragraph. A composed brief opens on
  // a "## Trades" heading, and that heading stays in the body where it
  // belongs rather than becoming the headline.
  const leadIndex = paragraphs.findIndex(
    (p) => p.trim() && !/^\s*#{1,6}\s/.test(p),
  );
  const first = leadIndex === -1 ? "" : paragraphs[leadIndex];
  const opening = firstSentence(first);
  if (!opening) return { headline: plain(md), deck: "", body: md };

  const { headline, standfirst } = splitLead(opening);
  const rest = first.slice(opening.length);
  const body = [
    ...paragraphs.slice(0, leadIndex),
    rest,
    ...paragraphs.slice(leadIndex + 1),
  ]
    .map((p) => p.trim())
    .filter(Boolean)
    .join("\n\n");

  return { headline, deck: standfirst, body };
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
    // Every section's stories, deduped: the composition is the whole edition's,
    // not just the league passage's.
    items: [
      ...new Map(
        brief.sections.flatMap((sec) => sec.stories).map((st) => [st.id, st]),
      ).values(),
    ],
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
    items: [],
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
