"""Assign articles to stories.

Backfill everything:  python -m worker.cluster          (cluster, then merge)
Hourly CI:            python -m worker.cluster --no-merge
Daily CI:             python -m worker.cluster --merge-only

Merging runs daily, not hourly: needs_merge accumulates the stories worth
looking at, so nothing is lost by batching a day of them into one pass.

Single-pass incremental assignment: each article joins the best-scoring story
in the candidate window, or seeds a new one. Deterministic given the same
corpus, because articles are processed in publication order -- without that,
re-running at a new threshold would produce differences you cannot attribute.
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from common.config import MERGE_THRESHOLD
from common.models import Story

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, text

from common.config import (
    ACCEPT_COSINE,
    CANDIDATE_MIN_COSINE,
    CANDIDATE_WINDOW_HOURS,
    MAX_MEMBER_GAP_DAYS,
    MAX_MERGE_GAP_DAYS,
    TIME_DECAY_SIGMA_HOURS,
)
from common.models import (
    Article,
    StoryMember,
    make_engine,
    make_session_factory,
    utcnow,
)

# Stories dormant this long stop accepting members. Event Registry uses 4 days;
# it bounds the candidate set permanently instead of letting it grow.
RETIRE_AFTER_DAYS = 4

# Cap on candidates scored per article. The SQL filter below is already exact,
# so this is a safety valve, not part of the algorithm.
CANDIDATE_LIMIT = 50


def article_time(article: Article) -> datetime:
    """When this article happened, per articles.effective_at.

    Reads the generated column rather than recomputing the fallback here, so
    clustering and the API can never disagree about an article's time -- they
    used to hold two copies of the same rule.
    """
    return article.effective_at


def time_factor(gap_hours: float) -> float:
    """Gaussian decay on the gap to a story's newest member.

    Miranda et al. (EMNLP 2018) tuned sigma to 72h and measured F1 92.7 -> 94.1
    from adding timestamp features. Measuring against the NEWEST member is what
    lets a live story keep accepting articles while a dormant one stops.
    """
    sigma = float(TIME_DECAY_SIGMA_HOURS)
    return math.exp(-(gap_hours**2) / (2 * sigma * sigma))


def candidate_stories(session, article: Article, when: datetime):
    """Stories that could plausibly absorb this article.

    Two routes in, unioned, scored as max(centroid cosine, best member cosine):

      - the story's CENTROID is close        (average linkage)
      - any single MEMBER is close           (single linkage)

    Centroid-only rejects an article that matches one member strongly but the
    cluster mean weakly -- the drift merge_pass() exists to clean up afterward.
    Taking the max catches it at assignment time instead.

    Two vector queries rather than one grouped join: joining every member of
    every candidate story runs once per article, and pgvector answers each of
    these directly.

    The floor is CANDIDATE_MIN_COSINE, deliberately looser than ACCEPT_COSINE,
    so nothing at or above the accept bar can be excluded.

    Returns (story_id, last_activity_at, cosine).
    """
    floor = 1.0 - CANDIDATE_MIN_COSINE
    window_start = when - timedelta(hours=CANDIDATE_WINDOW_HOURS)
    retire_cutoff = utcnow() - timedelta(days=RETIRE_AFTER_DAYS)
    best: dict[str, tuple[datetime, float]] = {}

    cdist = Story.centroid.cosine_distance(article.embedding)
    for sid, last_activity, dist in (
        session.query(Story.id, Story.last_activity_at, cdist.label("d"))
        .filter(
            Story.last_activity_at >= window_start,
            Story.last_activity_at >= retire_cutoff,
            cdist <= floor,
        )
        .order_by(cdist)
        .limit(CANDIDATE_LIMIT)
        .all()
    ):
        best[sid] = (last_activity, 1.0 - float(dist))

    mdist = Article.embedding.cosine_distance(article.embedding)
    for sid, last_activity, dist in (
        session.query(Story.id, Story.last_activity_at, mdist.label("d"))
        .select_from(Article)
        .join(StoryMember, StoryMember.article_id == Article.id)
        .join(Story, Story.id == StoryMember.story_id)
        .filter(
            Article.id != article.id,
            Story.last_activity_at >= window_start,
            Story.last_activity_at >= retire_cutoff,
            mdist <= floor,
        )
        .order_by(mdist)
        .limit(CANDIDATE_LIMIT * 4)
        .all()
    ):
        cosine = 1.0 - float(dist)
        previous = best.get(sid)
        if previous is None or cosine > previous[1]:
            best[sid] = (last_activity, cosine)

    return [(sid, la, cos) for sid, (la, cos) in best.items()]


def recompute_centroid(session, story: Story) -> None:
    """Recompute from members, entirely inside Postgres.

    Do NOT select the average into Python and assign it back -- a raw text()
    query returns the vector as a str, and pgvector's halfvec binder rejects
    strings. Updating in place also avoids shipping 384 floats out and back
    on every membership change.

    needs_merge rides along because this is the only place an existing
    story's centroid changes -- setting it here and at seed time is the whole
    contract merge_pass relies on.
    """
    session.execute(
        text(
            "UPDATE stories SET needs_merge = true, centroid = ("
            "  SELECT avg(a.embedding)::halfvec FROM articles a"
            "  JOIN story_members sm ON sm.article_id = a.id"
            "  WHERE sm.story_id = :sid"
            ") WHERE id = :sid"
        ),
        {"sid": story.id},
    )
    session.expire(story, ["centroid", "needs_merge"])


def assign(session, article: Article) -> Story:
    """Join the best-scoring story, or seed a new one.

    ACCEPT_COSINE gates on RAW cosine. The time factor only ranks which of the
    already-acceptable candidates wins -- inside MAX_MEMBER_GAP_DAYS it cannot
    veto one.

    Filter before ranking, not after. A weak near-in-time candidate can
    out-score a stronger distant one (cosine 0.64 at 0h scores 0.640; cosine
    0.70 at 40h scores 0.599), so testing only the winner's cosine would reject
    an article that had a perfectly good story available.

    The gap ceiling is the one exception, and it has to be a hard cutoff rather
    than a very low score: time_factor underflows to 0.0 far below the gaps it
    is meant to stop, and best_score starts at -1.0, so a candidate scoring
    exactly zero still wins whenever it is the only one above the cosine bar.
    """
    when = article_time(article)
    max_gap_hours = MAX_MEMBER_GAP_DAYS * 24

    best_story_id, best_cosine, best_score = None, 0.0, -1.0
    for story_id, last_activity, cosine in candidate_stories(session, article, when):
        if cosine < ACCEPT_COSINE:
            continue
        # abs(), so a feed that stamps an article in the future is bounded the
        # same way a stale republished one is.
        gap_hours = abs((when - last_activity).total_seconds()) / 3600.0
        if gap_hours > max_gap_hours:
            continue
        score = cosine * time_factor(gap_hours)
        if score > best_score:
            best_story_id, best_cosine, best_score = story_id, cosine, score

    if best_story_id is not None:
        story = session.get(Story, best_story_id)
        session.add(
            StoryMember(
                story_id=story.id, article_id=article.id, similarity=best_cosine
            )
        )
        session.flush()
        story.last_activity_at = max(story.last_activity_at, when)
        recompute_centroid(session, story)
        return story

    story = Story(
        title=article.headline,
        centroid=article.embedding,
        last_activity_at=when,
    )
    session.add(story)
    session.flush()  # populates story.id
    session.add(StoryMember(story_id=story.id, article_id=article.id, similarity=1.0))
    return story


def merge_pass(session) -> int:
    """Merge stories whose centroids have converged.

    Incremental assignment over-fragments by construction: an article is scored
    against a centroid that has already drifted toward existing members, so a
    late arrival worded differently seeds its own story. Your Gaza funeral split
    into a 7-outlet story and a 2-outlet wire-copy story for exactly this reason.

    Bloomberg's NSTM does the same two-stage thing -- over-fragment online,
    agglomerate afterward.

    SINGLE PASS, deliberately. Merging to a fixpoint lets A-B and B-C both be
    borderline and chain unrelated stories together.

    MERGE_THRESHOLD gates on RAW cosine, exactly as ACCEPT_COSINE does in
    assign(), and for the same reason. Testing cosine * decay against it made
    the bar age-dependent -- 0.79 at 24h, 0.94 at 48h, and above 1.0 from 72h,
    so no pair three days apart could merge however identical. Measured over
    315 candidate pairs, that refused about nine in ten real merges. The decay
    now only orders the pairs, and MAX_MERGE_GAP_DAYS is the bound.

    Vectors never leave Postgres. This used to SELECT every centroid and take
    a blocked NumPy product over them -- ~3 KB of vector-as-text per story per
    run, which at 15k stories, hourly, was most of Supabase's monthly egress
    budget by itself. pgvector computes the same cosines next to the data, and
    what crosses the wire is only the pairs that clear the bar: two ids and
    three timestamps each.

    Only stories flagged needs_merge are scored, and skipping the rest loses
    nothing. A pair with neither centroid changed got this exact comparison in
    an earlier pass and was refused then -- raw cosine gates, so its verdict
    cannot age. A pair the greedy loop below skips as `touched` always involves
    a keep whose centroid was just recomputed, which re-flags it for the next
    pass. Every genuinely new pair has a changed side, and changed sides are
    exactly what the flag records.
    """
    dirty = [
        r[0] for r in session.execute(text("SELECT id FROM stories WHERE needs_merge"))
    ]
    if not dirty:
        return 0

    # One dirty side, the partner anywhere in the gap window. When BOTH sides
    # are dirty the join yields the pair once per orientation, and the id
    # ordering keeps one; a dirty-vs-clean pair must survive whichever way its
    # ids happen to compare, hence the NOT. The distance filter runs where the
    # vectors live, which is the entire point of this query.
    candidates = session.execute(
        text(
            "SELECT a.id, a.last_activity_at, a.created_at,"
            "       b.id, b.last_activity_at, b.created_at,"
            "       1 - (a.centroid <=> b.centroid) AS cosine"
            "  FROM stories a"
            "  JOIN stories b ON b.id != a.id"
            "   AND (NOT b.needs_merge OR b.id > a.id)"
            "   AND b.last_activity_at BETWEEN a.last_activity_at - :gap"
            "                              AND a.last_activity_at + :gap"
            "   AND a.centroid <=> b.centroid <= :ceiling"
            " WHERE a.needs_merge"
        ),
        {"gap": timedelta(days=MAX_MERGE_GAP_DAYS), "ceiling": 1.0 - MERGE_THRESHOLD},
    ).all()

    # Clear the flags BEFORE the merges below re-flag their keeps: a story
    # that just absorbed another has a new centroid and belongs in the next
    # pass. Same transaction as the merges themselves, so a crash rolls back
    # both and the next pass simply redoes this one.
    session.execute(
        text("UPDATE stories SET needs_merge = false WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": dirty},
    )

    pairs = []
    for a_id, a_act, a_created, b_id, b_act, b_created, cosine in candidates:
        gap = abs((a_act - b_act).total_seconds()) / 3600.0
        pairs.append(
            (
                float(cosine) * time_factor(gap),
                (a_id, a_act, a_created),
                (b_id, b_act, b_created),
            )
        )

    # Ids as tiebreak, so equal scores cannot make the pass order-dependent.
    pairs.sort(key=lambda p: (-p[0], p[1][0], p[2][0]))
    touched: set[str] = set()
    merged = 0

    for _score, a, b in pairs:
        # Older story survives, so a story ID minted earlier keeps its meaning.
        keep, absorb = (a, b) if a[2] <= b[2] else (b, a)
        if keep[0] in touched or absorb[0] in touched:
            continue

        session.execute(
            text("UPDATE story_members SET story_id = :keep WHERE story_id = :absorb"),
            {"keep": keep[0], "absorb": absorb[0]},
        )
        session.execute(
            text(
                "UPDATE stories SET last_activity_at = greatest("
                "  (select last_activity_at from stories where id = :keep), :other"
                ") WHERE id = :keep"
            ),
            {"keep": keep[0], "other": absorb[1]},
        )
        # Everything a person made follows the merge. These cannot be left to
        # ON DELETE CASCADE the way story_categories is: a cascade would
        # silently destroy someone's saved story or their comment, and a merge
        # is a housekeeping decision the reader never asked for.
        session.execute(
            text("UPDATE comments SET story_id = :keep WHERE story_id = :absorb"),
            {"keep": keep[0], "absorb": absorb[0]},
        )
        # uq_favorites_user_story collides when the reader had already
        # favourited BOTH stories -- which is exactly the case a merge creates,
        # since the two were near-duplicates. Move what fits, drop the rest.
        session.execute(
            text(
                "UPDATE favorites SET story_id = :keep WHERE story_id = :absorb"
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM favorites f2"
                "     WHERE f2.user_id = favorites.user_id AND f2.story_id = :keep)"
            ),
            {"keep": keep[0], "absorb": absorb[0]},
        )
        session.execute(
            text("DELETE FROM favorites WHERE story_id = :absorb"),
            {"absorb": absorb[0]},
        )
        # story_categories needs nothing here -- its FK cascades (0011).
        session.execute(
            text("DELETE FROM stories WHERE id = :absorb"), {"absorb": absorb[0]}
        )
        recompute_centroid(session, session.get(Story, keep[0]))
        touched.update({keep[0], absorb[0]})
        merged += 1

    session.commit()
    return merged


def cluster_pending(session, limit: int | None = None) -> int:
    """Assign every embedded article that has no story yet.

    Publication order is load-bearing: whichever article arrives first seeds
    the story, so arbitrary ordering makes results irreproducible.
    """
    query = (
        session.query(Article)
        .outerjoin(StoryMember, StoryMember.article_id == Article.id)
        .filter(Article.embedding.is_not(None), StoryMember.id.is_(None))
        .order_by(Article.effective_at)
    )
    if limit is not None:
        query = query.limit(limit)

    total = 0
    for article in query.all():
        assign(session, article)
        session.commit()  # per article, so a crash keeps finished work
        total += 1
        if total % 200 == 0:
            print(f"  clustered {total}")
    return total


def main() -> int:
    reset = "--reset" in sys.argv
    merge_only = "--merge-only" in sys.argv
    no_merge = "--no-merge" in sys.argv
    Session = make_session_factory(make_engine())
    with Session() as session:
        if reset:
            host = urlparse(os.environ["DATABASE_URL"]).hostname or ""
            if host not in ("localhost", "127.0.0.1"):
                print(f"refusing to reset {host!r} -- localhost only")
                return 1
            session.execute(text("DELETE FROM story_members"))
            session.execute(text("DELETE FROM stories"))
            session.commit()
            print("cleared stories and story_members")

        if not merge_only:
            pending = (
                session.query(Article)
                .outerjoin(StoryMember, StoryMember.article_id == Article.id)
                .filter(Article.embedding.is_not(None), StoryMember.id.is_(None))
                .count()
            )
            print(
                f"{pending} articles to cluster  "
                f"(accept {ACCEPT_COSINE}, floor {CANDIDATE_MIN_COSINE}, "
                f"window {CANDIDATE_WINDOW_HOURS}h, sigma {TIME_DECAY_SIGMA_HOURS}h)"
            )
            if pending:
                print(f"done, {cluster_pending(session)} assigned")

        if not no_merge:
            merged = merge_pass(session)
            print(f"merge pass: {merged} stories absorbed")

        stories = session.query(Story).count()
        members = session.query(StoryMember).count()
        print(f"{stories} stories, {members} memberships")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
