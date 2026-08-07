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

from sqlalchemy import func, text

from common.config import (
    CANDIDATE_WINDOW_HOURS,
    SIMILARITY_THRESHOLD,
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
    """published_at is nullable -- some feeds omit it entirely."""
    return article.published_at or article.first_seen_at


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

    The cosine filter is EXACT, not an approximation: time_factor is always
    <= 1, so a story whose raw cosine is already below the threshold can never
    clear it after decay. That usually cuts thousands of rows to a handful.
    """
    dist = Story.centroid.cosine_distance(article.embedding)
    return (
        session.query(Story.id, Story.last_activity_at, dist.label("dist"))
        .filter(
            Story.last_activity_at >= when - timedelta(hours=CANDIDATE_WINDOW_HOURS),
            Story.last_activity_at >= utcnow() - timedelta(days=RETIRE_AFTER_DAYS),
            dist <= 1.0 - SIMILARITY_THRESHOLD,
        )
        .order_by(dist)
        .limit(CANDIDATE_LIMIT)
        .all()
    )


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
    """Join the best-scoring story, or seed a new one."""
    when = article_time(article)

    best_story_id, best_cosine, best_score = None, 0.0, 0.0
    for story_id, last_activity, dist in candidate_stories(session, article, when):
        cosine = 1.0 - float(dist)
        gap_hours = abs((when - last_activity).total_seconds()) / 3600.0
        score = cosine * time_factor(gap_hours)
        if score > best_score:
            best_story_id, best_cosine, best_score = story_id, cosine, score

    if best_story_id is not None and best_score >= SIMILARITY_THRESHOLD:
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
    """
    rows = session.query(
        Story.id, Story.centroid, Story.last_activity_at, Story.created_at
    ).all()
    if len(rows) < 2:
        return 0

    vectors = np.stack([_as_array(r[1]) for r in rows])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    sims = vectors @ vectors.T
    np.fill_diagonal(sims, 0.0)

    pairs = []
    for i, j in zip(*np.where(sims >= MERGE_THRESHOLD), strict=True):
        if i >= j:
            continue
        gap = abs((rows[i][2] - rows[j][2]).total_seconds()) / 3600.0
        score = float(sims[i, j]) * time_factor(gap)
        if score >= MERGE_THRESHOLD:
            pairs.append((score, i, j))

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
        .order_by(func.coalesce(Article.published_at, Article.first_seen_at))
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
            f"(threshold {SIMILARITY_THRESHOLD}, window {CANDIDATE_WINDOW_HOURS}h, "
            f"sigma {TIME_DECAY_SIGMA_HOURS}h)"
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
