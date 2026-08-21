import { formatDayStamp } from "../lib/dateline";
import type { StoryArticle } from "../types";

type OutletGroup = { outlet: string; articles: StoryArticle[] };

/**
 * Group articles by outlet, outlets ordered by who published first.
 *
 * The API returns articles chronologically, so a Map preserves exactly that
 * ordering for free -- the first time an outlet appears is its first
 * publication. No sorting needed, and none should be added: "who broke it"
 * is the ordering the product is about.
 */
function groupByOutlet(articles: StoryArticle[]): OutletGroup[] {
  const byOutlet = new Map<string, StoryArticle[]>();
  for (const article of articles) {
    const existing = byOutlet.get(article.outlet);
    if (existing) existing.push(article);
    else byOutlet.set(article.outlet, [article]);
  }
  return [...byOutlet].map(([outlet, group]) => ({ outlet, articles: group }));
}

/** "+0h", "+3h", "+2d" -- time since the first outlet published. */
function offset(firstMs: number, iso: string): string {
  const hours = (Date.parse(iso) - firstMs) / 3_600_000;
  if (hours < 1) return `+${Math.round(hours * 60)}m`;
  if (hours < 48) return `+${Math.round(hours)}h`;
  return `+${Math.round(hours / 24)}d`;
}

function Chevron() {
  return (
    <svg
      viewBox="0 0 12 12"
      className="h-2.5 w-2.5 shrink-0 text-ink-mute transition-transform group-open:rotate-90"
      aria-hidden="true"
    >
      <path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

/**
 * Who covered this, and when -- plotted rather than listed.
 *
 * This is the surface the design doc calls the differentiator, and it was a
 * disclosure list in a rounded box: it could tell you an outlet filed at +3h,
 * but never that eleven outlets went within the first hour and the twelfth
 * arrived two days later. That shape is the whole claim, and a list cannot
 * make it.
 *
 * One row per outlet, ordered by who published first. The track is the story's
 * own lifespan end to end; every article is a tick at its true position on it.
 * An outlet's FIRST tick is spot ink -- the moment they went -- and its later
 * filings are quiet marks, so the eye reads the front edge of the coverage
 * before it reads the volume behind it. That is the same job the freshness
 * rule does on the front page: a rule that measures something real.
 *
 * Rows stay expandable, because when an outlet went is half the question and
 * what they said is the other half.
 */
export function StoryTimeline({
  articles,
  firstAt,
  lastAt,
}: {
  articles: StoryArticle[];
  firstAt: string;
  lastAt: string;
}) {
  const groups = groupByOutlet(articles);
  const firstMs = Date.parse(firstAt);
  const lastMs = Date.parse(lastAt);

  // 46 of 200 eligible stories have a span of exactly zero -- every outlet
  // filed inside the same rounding window. Dividing by that span is a NaN on
  // nearly a quarter of the corpus, so the degenerate case is decided here
  // rather than guarded at every use: the track collapses, every tick sits at
  // the head of it, and the axis says one date instead of pretending to a
  // range it does not have.
  const duration = lastMs - firstMs;
  const flat = !Number.isFinite(duration) || duration <= 0;

  const position = (iso: string): number => {
    if (flat) return 0;
    const at = (Date.parse(iso) - firstMs) / duration;
    // Clamp rather than trust: a member article timestamped outside the
    // story's own range would otherwise render off the track entirely.
    return Math.min(1, Math.max(0, at)) * 100;
  };

  return (
    <div>
      <ul>
        {groups.map((group) => (
          <li key={group.outlet} className="border-t border-rule">
            <details className="group">
              <summary className="flex cursor-pointer list-none items-center gap-3 py-2.5 [&::-webkit-details-marker]:hidden">
                <Chevron />

                <span className="t-wire w-28 shrink-0 truncate text-ink sm:w-44">
                  {group.outlet}
                </span>

                {/* The track is the paper; only the ticks are inked. */}
                <span className="relative h-4 min-w-0 flex-1">
                  <span
                    aria-hidden="true"
                    className="absolute top-1/2 right-0 left-0 h-px -translate-y-1/2 bg-rule"
                  />
                  {group.articles.map((article, i) => (
                    <span
                      key={`${article.url}-${i}`}
                      aria-hidden="true"
                      className={`absolute top-1/2 w-px -translate-x-1/2 -translate-y-1/2 ${
                        i === 0 ? "h-4 bg-spot" : "h-2.5 bg-ink-mute"
                      }`}
                      style={{ left: `${position(article.published_at)}%` }}
                    />
                  ))}
                </span>

                <span className="t-wire w-8 shrink-0 text-right text-ink-mute">
                  {group.articles.length}
                </span>
                <span className="t-wire w-10 shrink-0 text-right text-ink">
                  {offset(firstMs, group.articles[0].published_at)}
                </span>
              </summary>

              <ol className="pb-3 pl-8">
                {group.articles.map((article, i) => (
                  <li key={`${article.url}-${i}`} className="flex gap-3 pt-2">
                    <span className="t-wire w-10 shrink-0 text-right text-ink-mute">
                      {offset(firstMs, article.published_at)}
                    </span>
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noreferrer"
                      className="t-read min-w-0 text-[0.9375rem] text-ink decoration-1 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
                    >
                      {article.headline}
                    </a>
                  </li>
                ))}
              </ol>
            </details>
          </li>
        ))}
      </ul>

      {/* The axis, under the tracks and inset to line up with them. */}
      <div className="border-t border-rule pt-2 pl-[calc(0.625rem+0.75rem)]">
        <div className="flex items-baseline gap-3">
          <span className="w-28 shrink-0 sm:w-44" />
          <span className="t-wire flex min-w-0 flex-1 justify-between text-ink-mute">
            <span>{formatDayStamp(firstAt)}</span>
            {!flat && <span>{formatDayStamp(lastAt)}</span>}
          </span>
          <span className="w-8 shrink-0" />
          <span className="w-10 shrink-0" />
        </div>
      </div>
    </div>
  );
}
