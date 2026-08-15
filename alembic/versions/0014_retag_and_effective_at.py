"""categorisation bookkeeping, and articles.effective_at

Revision ID: 0014
Revises: 0013

Three fixes that all needed a column.

1. Stale tags after a merge. stories_needing_categories selected on "has no
   story_categories row", so a story was tagged once and never revisited. Its
   member set changes every time merge_pass folds another story into it, and
   the tags go on describing the old one. summarize already solved this with
   summarized_at + summarized_outlet_count and a growth factor; these are the
   same two columns for categories. Existing tagged stories are backfilled so
   the change does not re-tag all of them on the next run.

2. Stories the model cannot tag were retried forever. Nothing was written on
   failure, so the story was selected again next run -- and since the query
   orders by outlet count, it returned to the FRONT of the queue every time.
   category_attempts bounds that. Recording categorized_outlet_count on a
   failed attempt too is what lets a story that later grows be reconsidered
   rather than written off permanently.

3. articles.effective_at. published_at comes from the feed and is left alone;
   this is the derived answer to "when did this happen" that eleven queries
   across six files were each computing for themselves with
   coalesce(published_at, first_seen_at). Generated rather than written at
   ingest so it cannot drift from its inputs, and so the policy lives in one
   place -- which matters because the policy is not finished. It corrects only
   what is impossible (a feed dating an item after we fetched it, 14 rows
   today) and NOT the merely implausible: an item stamped weeks before we saw
   it may be a republished evergreen or may be one we were simply late to
   fetch, and nothing in the data separates those. Improving that later is now
   one migration instead of eleven edits.
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_EFFECTIVE_AT = """
    case
        when published_at is null then first_seen_at
        when published_at > first_seen_at then first_seen_at
        else published_at
    end
"""


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("categorized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "stories", sa.Column("categorized_outlet_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "stories",
        sa.Column(
            "category_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # Without this every already-tagged story looks untagged to the new query
    # and burns a model call re-deriving tags it already has.
    op.execute("""
        update stories s
           set categorized_at = now(),
               categorized_outlet_count = (
                   select count(distinct a.outlet_id)
                     from story_members sm
                     join articles a on a.id = sm.article_id
                    where sm.story_id = s.id)
         where exists (select 1 from story_categories sc where sc.story_id = s.id)
    """)

    op.add_column(
        "articles",
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            sa.Computed(_EFFECTIVE_AT, persisted=True),
            nullable=False,
        ),
    )
    # Ordering by time is the single most common thing done to this table.
    op.create_index("ix_articles_effective_at", "articles", ["effective_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_effective_at", table_name="articles")
    op.drop_column("articles", "effective_at")
    op.drop_column("stories", "category_attempts")
    op.drop_column("stories", "categorized_outlet_count")
    op.drop_column("stories", "categorized_at")
