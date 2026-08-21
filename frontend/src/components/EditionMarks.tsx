import type { CSSProperties } from "react";
import { teamInk } from "../lib/teamColors";
import type { BriefStory } from "../types";

/** How many clubs get their own bar before the rest fold into one. */
const SHOWN = 4;

type Share = { code: string; count: number; share: number };

/**
 * What the edition is about, and how widely it was reported.
 *
 * Composition first, because that is the question a reader actually has about
 * a personalised brief: whose news is this. Shares are by STORY, not by word
 * count -- a story is the unit the reader is being served, and word count
 * would let one long passage claim the whole edition.
 *
 * A story tagged to several clubs counts once for each: a four-team trade IS
 * about four clubs, and forcing it onto its top-ranked one would report the
 * day wrongly to be able to make the percentages total a hundred. So they do
 * not total a hundred, and the label says "of the stories" rather than
 * printing a total that would be a lie.
 */
function shares(stories: BriefStory[]): { rows: Share[]; rest: number } {
  const counts = new Map<string, number>();
  for (const story of stories) {
    for (const code of story.teams) {
      counts.set(code, (counts.get(code) ?? 0) + 1);
    }
  }
  const total = stories.length || 1;
  const all = [...counts]
    .map(([code, count]) => ({ code, count, share: count / total }))
    .sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));

  return { rows: all.slice(0, SHOWN), rest: all.length - SHOWN };
}

/**
 * How concentrated the sourcing was.
 *
 * The one figure adjacent to what people mean when they ask for bias, without
 * importing a lean score somebody else has to defend: not who leans which way,
 * but how few outlets the day actually came from. Every number here is counted,
 * not judged.
 */
function sourcing(stories: BriefStory[]): { outlets: number; top: string | null; topIn: number } {
  const seen = new Map<string, number>();
  for (const story of stories) {
    for (const name of story.outlets) {
      seen.set(name, (seen.get(name) ?? 0) + 1);
    }
  }
  const ranked = [...seen].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return {
    outlets: seen.size,
    top: ranked[0]?.[0] ?? null,
    topIn: ranked[0]?.[1] ?? 0,
  };
}

/**
 * The plate's data marks.
 *
 * Bars rather than a pie: comparing angles is the hardest visual judgement
 * there is, and at four to six clubs a pie is a fan of slivers. Length against
 * a common baseline is the easiest, which is the whole reason to prefer it.
 *
 * Every bar is directly labelled with its club code. That is not decoration --
 * it is what makes the colour legal. The league has four reds and six blues,
 * and no tuning separates two crimsons for a colourblind reader, so identity
 * is carried by the label and colour reinforces it. See lib/teamColors.
 */
export function EditionMarks({
  stories,
  personal,
}: {
  stories: BriefStory[];
  /** True when the reader follows teams, so this really is theirs. */
  personal: boolean;
}) {
  const { rows, rest } = shares(stories);
  if (rows.length === 0) return null;

  const source = sourcing(stories);

  return (
    <div className="pt-6">
      <p className="t-wire pb-2 text-ink-mute">
        {personal ? "Your edition" : "This edition"}
      </p>

      <ul>
        {rows.map((row) => (
          <li key={row.code} className="flex items-center gap-2.5 py-[3px]">
            <span className="t-wire w-8 shrink-0 text-ink">{row.code}</span>
            {/* Proportional from a common zero, NOT scaled to the widest bar.
                Scaling to the max drew every bar at full width on a day that
                split evenly, under a label reading 20% -- the length said one
                thing and the number said another. A short bar is the honest
                answer when the day really was even. */}
            <span className="min-w-0 flex-1">
              <span
                className="team-fill block h-2"
                style={
                  {
                    ...teamInk(row.code),
                    width: `${Math.max(2, row.share * 100)}%`,
                  } as CSSProperties
                }
              />
            </span>
            <span className="t-wire w-10 shrink-0 text-right text-ink-mute">
              {Math.round(row.share * 100)}%
            </span>
          </li>
        ))}
      </ul>

      <p className="t-wire pt-3 text-ink-mute">
        {rest > 0 && (
          <>
            +{rest} more
            <span aria-hidden="true"> · </span>
          </>
        )}
        {source.outlets} outlet{source.outlets === 1 ? "" : "s"}
        {source.top && (
          <>
            <span aria-hidden="true"> · </span>
            {source.top} {source.topIn}/{stories.length}
          </>
        )}
      </p>
    </div>
  );
}
