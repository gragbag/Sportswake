"""Score every recent story on how much it deserves a brief.

Run locally:   python -m worker.importance
Run in CI:     after categorize in Ingest.yml, and every tick of briefs.yml

    importance = w1 * corroboration   (distinct sources, saturating)
               + w2 * recency         (Gaussian decay on last activity)
               + w3 * authority       (best outlet on the story)
               + w4 * has_game        (0 or 1)

Computed, never asked of a model. This is the gate the whole product rests
on -- "only significant news" is enforced here, and a brief that pads itself
with minor items has failed. Letting an LLM rate its own story's importance
would make the gate advisory, because it would inflate.

Two decisions worth knowing before changing anything here:

CORROBORATION COUNTS DISTINCT TEXT, NOT DISTINCT OUTLETS. Nine outlets
running one AP wire story is one newsroom's reporting, nine times. Under the
old design outlet count was only ever a floor (>= 2 to display, >= 5 to
summarize) so syndication merely let a story through a door; as a continuous
weight it would inflate the score every time it is computed, and inflate it
most for the wire stories that least deserve a brief.

RECOMPUTATION IS A ROLLING WINDOW, NOT A DIRTY FLAG. `needs_merge` works
because a centroid changes only on a write. This score does not have that
property: the recency term decays with the clock while nothing writes. A
flag-driven version would freeze idle stories at a stale, inflated value --
and those values are the population the major-story percentile is drawn
from, so the error would spread from selection into the word budget too.

Because it is pure arithmetic with no LLM in the loop, the whole thing is one
set-based UPDATE rather than the per-story Python loop the LLM workers need.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import (
    IMPORTANCE_DECAY_SIGMA_HOURS,
    IMPORTANCE_RECOMPUTE_WINDOW_DAYS,
    IMPORTANCE_SOURCE_SATURATION,
    IMPORTANCE_THRESHOLD,
    IMPORTANCE_W_AUTHORITY,
    IMPORTANCE_W_GAME,
    IMPORTANCE_W_RECENCY,
    IMPORTANCE_W_SOURCES,
)
from common.models import make_engine, make_session_factory

# Resolved from team plus ET date, in SQL, never by the model. A hallucinated
# game id would put fabricated numbers into a brief through the one door the
# whole design keeps sealed -- so the link is only ever drawn between rows
# that already exist on both sides.
_LINK_GAMES = """
    update stories s
    set linked_game_id = g.id
    from games g
    where s.linked_game_id is null
      and s.last_activity_at >= now() - make_interval(days => :window_days)
      and g.game_date_et = (s.last_activity_at at time zone 'America/New_York')::date
      and exists (
            select 1 from story_teams st
            where st.story_id = s.id
              and st.team_code in (g.home_team_code, g.away_team_code)
      )
"""

# One statement, one pass. Each term is clamped to 0-1 on its own before the
# weights are applied, so the sum cannot exceed 1 and never needs rescaling.
_SCORE = """
    with agg as (
        select s.id,
               -- Distinct TEXT, not distinct outlets: collapses wire copy.
               -- Falls back to the article id so rows ingested before
               -- content_hash existed still count as themselves.
               count(distinct coalesce(a.content_hash, a.id::text)) as sources,
               max(o.authority_weight) as authority
        from stories s
        join story_members sm on sm.story_id = s.id
        join articles a on a.id = sm.article_id
        join outlets o on o.id = a.outlet_id
        where s.last_activity_at >= now() - make_interval(days => :window_days)
        group by s.id
    )
    update stories s
    set importance_score =
            :w_sources * least(1.0, ln(1 + agg.sources) / ln(1 + :saturation))
          + :w_recency * exp(
                -power(
                    extract(epoch from (now() - s.last_activity_at)) / 3600.0, 2
                ) / (2 * :sigma * :sigma)
            )
          + :w_authority * least(1.0, greatest(0.0, coalesce(agg.authority, 0)))
          + :w_game * (case when s.linked_game_id is not null then 1 else 0 end),
        importance_computed_at = now()
    from agg
    where agg.id = s.id
"""

# Ratchet: peak only ever moves up. Run immediately after scoring, in the same
# pass, so a story's high-water mark is recorded before the recency term
# starts pulling its live score back down.
_PEAK = """
    update stories
    set importance_peak = greatest(importance_peak, importance_score)
    where last_activity_at >= now() - make_interval(days => :window_days)
      and importance_score > importance_peak
"""


def link_games(session, window_days: int = IMPORTANCE_RECOMPUTE_WINDOW_DAYS) -> int:
    """Attach stories to the game they are about, where one exists.

    A story matching two games on one ET date resolves to an arbitrary one.
    That is acceptable for a 0/1 term in a score; it is NOT acceptable as the
    source of a quoted stat, which is why the generator re-reads the box score
    for whichever game it links rather than trusting this to be the only one.
    """
    result = session.execute(text(_LINK_GAMES), {"window_days": window_days})
    session.commit()
    return result.rowcount or 0


def score_stories(session, window_days: int = IMPORTANCE_RECOMPUTE_WINDOW_DAYS) -> int:
    result = session.execute(
        text(_SCORE),
        {
            "window_days": window_days,
            "saturation": IMPORTANCE_SOURCE_SATURATION,
            "sigma": float(IMPORTANCE_DECAY_SIGMA_HOURS),
            "w_sources": IMPORTANCE_W_SOURCES,
            "w_recency": IMPORTANCE_W_RECENCY,
            "w_authority": IMPORTANCE_W_AUTHORITY,
            "w_game": IMPORTANCE_W_GAME,
        },
    )
    session.execute(text(_PEAK), {"window_days": window_days})
    session.commit()
    return result.rowcount or 0


def report(session, window_days: int) -> None:
    """Print the distribution, because a threshold set without seeing one is
    a guess. This is the output the eligibility floor should be tuned from."""
    row = session.execute(
        text("""
            select count(1) as n,
                   round(min(importance_score)::numeric, 3) as lo,
                   round(avg(importance_score)::numeric, 3) as mean,
                   round(max(importance_score)::numeric, 3) as hi,
                   count(1) filter (where importance_score >= :threshold) as eligible
            from stories
            where last_activity_at >= now() - make_interval(days => :window_days)
        """),
        {"window_days": window_days, "threshold": IMPORTANCE_THRESHOLD},
    ).one()
    print(
        f"  scored {row.n}: min {row.lo}, mean {row.mean}, max {row.hi}\n"
        f"  >= {IMPORTANCE_THRESHOLD} (eligible): {row.eligible}"
    )

    print("  top stories:")
    for r in session.execute(
        text("""
            select round(importance_score::numeric, 3) as score,
                   coalesce(summary_title, title) as title
            from stories
            where last_activity_at >= now() - make_interval(days => :window_days)
            order by importance_score desc
            limit 8
        """),
        {"window_days": window_days},
    ):
        print(f"    {r.score}  {(r.title or '')[:76]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute story importance.")
    parser.add_argument(
        "--window-days",
        type=int,
        default=IMPORTANCE_RECOMPUTE_WINDOW_DAYS,
        help="How far back to rescore. Older stories keep their last score.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the score distribution, for tuning IMPORTANCE_THRESHOLD.",
    )
    args = parser.parse_args()

    engine = make_engine()
    Session = make_session_factory(engine)

    with Session() as session:
        linked = link_games(session, args.window_days)
        if linked:
            print(f"Linked {linked} stories to games")

        scored = score_stories(session, args.window_days)
        print(f"Scored {scored} stories")

        if args.report:
            report(session, args.window_days)

    return 0


if __name__ == "__main__":
    # Headlines carry en dashes, non-breaking hyphens and accented names, and
    # a Windows console defaults to cp1252 -- which raises rather than
    # substitutes. Diagnostics must never be the thing that kills a run, so
    # this is set on the script path only, not at import.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    raise SystemExit(main())
