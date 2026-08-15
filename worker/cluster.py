"""Assign articles to stories.

Backfill everything:  python -m worker.cluster
During ingestion:     ingest.py calls cluster_pending() after embed_pending().

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

import numpy as np

from common.config import MERGE_THRESHOLD
from common.models import Story

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

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

# Rows of the similarity product held at once in merge_pass. Memory is
# MERGE_BLOCK x stories x 4 bytes -- ~126 MB at today's 15.7k stories, and it
# grows linearly rather than quadratically. Purely a memory knob: the pairs
# found do not depend on it.
MERGE_BLOCK = 2000


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
    """
    session.execute(
        text(
            "UPDATE stories SET centroid = ("
            "  SELECT avg(a.embedding)::halfvec FROM articles a"
            "  JOIN story_members sm ON sm.article_id = a.id"
            "  WHERE sm.story_id = :sid"
            ") WHERE id = :sid"
        ),
        {"sid": story.id},
    )
    session.expire(story, ["centroid"])


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


def _as_array(centroid) -> np.ndarray:
    """Centroids come back as ndarray via the ORM but as a string from raw SQL."""
    if isinstance(centroid, str):
        return np.fromstring(centroid.strip("[]"), sep=",", dtype=np.float32)
    return np.asarray(centroid, dtype=np.float32)


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
    """
    rows = session.query(
        Story.id, Story.centroid, Story.last_activity_at, Story.created_at
    ).all()
    if len(rows) < 2:
        return 0

    # End the read transaction before the arithmetic starts. Everything below
    # is CPU, and holding a transaction across it leaves the connection "idle
    # in transaction" for minutes -- long enough to block any ALTER TABLE that
    # comes along, which is exactly how this was found. The writes further
    # down open a fresh transaction of their own.
    session.rollback()

    vectors = np.stack([_as_array(r[1]) for r in rows]).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    stamps = np.array([r[2].timestamp() for r in rows], dtype=np.float64)
    max_gap_hours = MAX_MERGE_GAP_DAYS * 24

    # Blocked, rather than one n x n matrix. The full product is ~1 GB at 15k
    # stories and grows quadratically; peak here is MERGE_BLOCK rows wide, so
    # memory stops depending on how big the corpus has got.
    pairs = []
    for start in range(0, len(rows), MERGE_BLOCK):
        block = vectors[start : start + MERGE_BLOCK] @ vectors.T
        for offset in range(block.shape[0]):
            i = start + offset
            # j > i keeps each pair once and drops the diagonal with it, which
            # is what fill_diagonal(0) used to be for.
            js = np.where(block[offset] >= MERGE_THRESHOLD)[0]
            for j in js[js > i]:
                gap = abs(stamps[j] - stamps[i]) / 3600.0
                if gap > max_gap_hours:
                    continue
                score = float(block[offset][j]) * time_factor(gap)
                pairs.append((score, i, int(j)))
        del block

    pairs.sort(reverse=True)
    touched: set[str] = set()
    merged = 0

    for _score, i, j in pairs:
        # Older story survives, so a story ID minted earlier keeps its meaning.
        keep, absorb = (
            (rows[i], rows[j]) if rows[i][3] <= rows[j][3] else (rows[j], rows[i])
        )
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
            {"keep": keep[0], "other": absorb[2]},
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

        merged = merge_pass(session)
        print(f"merge pass: {merged} stories absorbed")

        stories = session.query(Story).count()
        members = session.query(StoryMember).count()
        print(f"{stories} stories, {members} memberships")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
