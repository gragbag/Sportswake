"""HNSW indexes on the embedding columns

Revision ID: 0020
Revises: 0019

Until now every similarity query in this codebase has been an exact scan.
That was defensible while the corpus was small -- cluster.py already bounds
its candidate set by time window and LIMIT, so the sequential scan was over
a few thousand rows -- but it is linear in corpus size, and the corpus is the
one thing this project is designed to grow forever.

halfvec, not vector: the columns are already HALFVEC(384) from 0002/0003, and
pgvector's halfvec_cosine_ops indexes them natively. Verified against the
live database before writing this -- pgvector 0.8.2 on Postgres 17.6, opclass
present. No type change, so this migration adds indexes and nothing else.

Cosine, matching the operator the queries actually use (`<=>`). An index
built for a distance function the query does not use is silently never
consulted, which looks exactly like the index working and not helping.

Default m/ef_construction. Tuning them before there is enough data to measure
a recall difference would be guessing, and the defaults are what pgvector
recommends until measurement says otherwise.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Not CONCURRENTLY: Alembic runs migrations inside a transaction, and
    # CREATE INDEX CONCURRENTLY cannot run in one. At current corpus size
    # this builds in well under a second; if that stops being true, the fix
    # is a separate out-of-band build, not a partial transaction here.
    op.execute(
        "create index ix_articles_embedding_hnsw "
        "on articles using hnsw (embedding halfvec_cosine_ops)"
    )
    op.execute(
        "create index ix_stories_centroid_hnsw "
        "on stories using hnsw (centroid halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("drop index if exists ix_stories_centroid_hnsw")
    op.execute("drop index if exists ix_articles_embedding_hnsw")
