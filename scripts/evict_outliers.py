"""Remove cluster members that are temporally isolated from their story.

    make evict            # dry run -- prints what it would delete
    make evict APPLY=1    # actually deletes

Cleanup for stories clustered BEFORE the MAX_MEMBER_GAP_DAYS ceiling landed in
worker.cluster. Those runs let an article join a story on cosine alone, so a
2024 evergreen explainer, re-served into an RSS feed on a 2026 news cycle,
became the first_at of a live story -- which is what the card reports as "who
broke it" and what the story page measures every other article against.

This is deliberately NOT `cluster --reset`. That drops every story and rebuilds
with fresh UUIDs, which destroys all summaries (they are columns on stories),
all category tags, and every favorite, comment, and permalink pointing at a
story id. Deleting the offending story_members rows leaves story identity
untouched: first_at, span_hours and the outlet ordering are computed from
members at query time, so the fix shows up immediately with nothing to rebuild.

Unlike worker.summarize and worker.categorize, the default here is the dry run.
Those are idempotent additive workers on a cron; this is a one-shot DELETE
against production, so acting has to be the thing you opt into.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from common.config import MAX_MEMBER_GAP_DAYS
from common.models import Story, make_engine, make_session_factory
from worker.cluster import recompute_centroid

# Retrospective analogue of the assign()-time gap. That one measures against
# the story's newest member AT THE MOMENT the article arrived, which is not
# recoverable after the fact; the gap to the nearest clustermate in either
# direction is, and it identifies the same articles -- an outlier is one no
# other member sits near, whenever it happened to be assigned.
#
# members > 1 excludes singletons, whose lag/lead are both null and would
# otherwise every one of them look infinitely isolated.
OUTLIERS = """
    with m as (
      select sm.id, sm.story_id, sm.article_id,
             coalesce(a.published_at, a.first_seen_at) as ts,
             count(*) over (partition by sm.story_id) as members
      from story_members sm
      join articles a on a.id = sm.article_id
    ),
    g as (
      select id, story_id, article_id, ts, members,
             least(
               coalesce(ts - lag(ts) over (partition by story_id order by ts),
                        interval '99 years'),
               coalesce(lead(ts) over (partition by story_id order by ts) - ts,
                        interval '99 years')
             ) as gap
      from m
      where members > 1
    )
    select g.id, g.story_id, g.ts, g.gap, g.members,
           o.name as outlet, a.headline, a.first_seen_at,
           coalesce(s.summary_title, s.title) as story_title
    from g
    join articles a on a.id = g.article_id
    join outlets o on o.id = a.outlet_id
    join stories s on s.id = g.story_id
    where g.gap > make_interval(days => :max_gap)
    order by g.gap desc
"""


def main() -> int:
    apply = "--apply" in sys.argv
    Session = make_session_factory(make_engine())

    with Session() as session:
        rows = session.execute(text(OUTLIERS), {"max_gap": MAX_MEMBER_GAP_DAYS}).all()

        if not rows:
            print(f"nothing isolated by more than {MAX_MEMBER_GAP_DAYS}d")
            return 0

        print(
            f"{len(rows)} member(s) isolated by more than {MAX_MEMBER_GAP_DAYS}d"
            f"{'' if apply else '  [DRY RUN -- pass --apply to delete]'}"
        )
        for r in rows:
            lag = (r.first_seen_at - r.ts).days
            print(f"\n  gap {r.gap.days}d  |  1 of {r.members} members")
            print(f"    story:   {r.story_title[:66]}")
            print(f"    remove:  [{r.outlet}] {r.headline[:58]}")
            print(
                f"             published {r.ts:%Y-%m-%d}, first seen "
                f"{r.first_seen_at:%Y-%m-%d} ({lag}d later)"
            )

        if not apply:
            return 0

        session.execute(
            text("delete from story_members where id = any(:ids)"),
            {"ids": [r.id for r in rows]},
        )

        # Both denormalised columns have to follow the membership change.
        # last_activity_at matters because the gap test is absolute: a feed
        # that stamps an article in the FUTURE makes it the story's newest
        # member, so evicting it leaves last_activity_at ahead of every
        # remaining article and the story accepting members it should not.
        for story_id in {r.story_id for r in rows}:
            story = session.get(Story, story_id)
            if story is None:
                continue
            recompute_centroid(session, story)
            session.execute(
                text(
                    "update stories set last_activity_at = ("
                    "  select max(coalesce(a.published_at, a.first_seen_at))"
                    "  from articles a"
                    "  join story_members sm on sm.article_id = a.id"
                    "  where sm.story_id = :sid"
                    ") where id = :sid"
                ),
                {"sid": story_id},
            )

        session.commit()
        stories = len({r.story_id for r in rows})
        print(
            f"\ndeleted {len(rows)} member(s); recomputed {stories} story centroid(s)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
