"""categories and story_categories

Revision ID: 0010
Revises: 0009

A many-to-many rather than an array column on stories. The deciding reason
is not performance -- at this corpus size neither is measurable -- but that
adding a ninth category becomes an INSERT rather than a migration to change
a CHECK constraint.

The slug is the primary key, so story_categories carries a readable value
and a tab query never has to join this table. That recovers most of what an
array would have given while keeping the taxonomy as data.

The eight seeded here are reference data, deliberately in the migration:
they are what the prompt is built from, so a database without them cannot
categorise anything.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# What KIND of story, not who it is about -- teams live in their own table
# (0013) and the classifier returns both from one call. Seven, because the
# corpus is one league: a taxonomy wide enough for general news would leave
# most tabs empty here.
#
# Ordered by how much of the corpus each is expected to hold, so the busiest
# tabs sit leftmost.
_SEED = [
    ("games", "Games", 1),
    ("trades", "Trades", 2),
    ("free-agency", "Free Agency", 3),
    ("injuries", "Injuries", 4),
    ("draft", "Draft", 5),
    ("business", "Business", 6),
    ("off-court", "Off Court", 7),
]


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("slug", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("sort_order", sa.SmallInteger, nullable=False),
    )
    op.bulk_insert(
        categories,
        [{"slug": s, "label": lbl, "sort_order": n} for s, lbl, n in _SEED],
    )

    op.create_table(
        "story_categories",
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id"),
            primary_key=True,
        ),
        sa.Column(
            "category_slug",
            sa.String(32),
            sa.ForeignKey("categories.slug"),
            primary_key=True,
        ),
        # 0 is primary -- shown when there is only room for one label.
        sa.Column("rank", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # The primary key leads with story_id, which serves "what is this story
    # tagged with". The tab query asks the opposite -- "what is in this
    # category" -- and needs the slug to lead.
    op.create_index(
        "ix_story_categories_slug", "story_categories", ["category_slug", "story_id"]
    )

    for table in ("categories", "story_categories"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_story_categories_slug", table_name="story_categories")
    op.drop_table("story_categories")
    op.drop_table("categories")
