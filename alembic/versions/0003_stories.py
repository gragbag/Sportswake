"""stories and story members

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("title", sa.Text),
        sa.Column("centroid", HALFVEC(384), nullable=False),
        # The newest coalesce(published_at, first_seen_at) across members.
        # Does double duty: filters the candidate window, and is the timestamp
        # the Gaussian time decay measures against.
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_stories_last_activity", "stories", ["last_activity_at"])

    op.create_table(
        "story_members",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "story_id", UUID(as_uuid=False), sa.ForeignKey("stories.id"), nullable=False
        ),
        # Unique: an article belongs to exactly one story, which makes
        # "what is unclustered" a LEFT JOIN. Story-level merges arrive later
        # via merged_into_id and never rewrite these rows.
        sa.Column(
            "article_id",
            UUID(as_uuid=False),
            sa.ForeignKey("articles.id"),
            nullable=False,
            unique=True,
        ),
        # Raw cosine, NOT the time-decayed score. Storing the composite would
        # make replaying clustering at a different sigma impossible.
        sa.Column("similarity", sa.Float, nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_story_members_story", "story_members", ["story_id"])


def downgrade() -> None:
    op.drop_table("story_members")
    op.drop_table("stories")
