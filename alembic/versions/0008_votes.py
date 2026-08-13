"""comment votes and comment-history privacy

Revision ID: 0008
Revises: 0007

Votes are stored as +1/-1 rows rather than a counter on the comment. The net
score is a sum, but ups and downs stay separately countable -- which matters
because ranking by raw score has a known flaw (3 upvotes out of 3 outranks
200 out of 220, and early comments accumulate a lead later ones cannot
catch). Switching to a confidence-interval sort later is then a change to
one ORDER BY, not a migration.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comment_votes",
        # Composite PK: one vote per person per comment, enforced by the
        # database, and changing your mind is an upsert rather than a
        # read-modify-write that could race.
        sa.Column(
            "comment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("comments.id"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("value", sa.SmallInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Only two values are meaningful; anything else is a bug upstream.
        sa.CheckConstraint("value in (-1, 1)", name="ck_comment_votes_value"),
    )
    op.create_index("ix_comment_votes_comment", "comment_votes", ["comment_id"])

    # Opt-out rather than opt-in: individual comments are already public on
    # the story page, so this hides the aggregated view, not the content.
    op.add_column(
        "profiles",
        sa.Column(
            "hide_comment_history",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute("ALTER TABLE public.comment_votes ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_column("profiles", "hide_comment_history")
    op.drop_index("ix_comment_votes_comment", table_name="comment_votes")
    op.drop_table("comment_votes")
