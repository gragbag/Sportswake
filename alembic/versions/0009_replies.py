"""comment replies, author deletion

Revision ID: 0009
Revises: 0008

Adds threading plus a 'deleted' status distinct from 'removed': one is the
author withdrawing their words, the other is moderation. Both leave a
tombstone when the comment has replies, because dropping the row would
orphan every answer beneath it and the conversation stops making sense.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Self-referential and nullable: null means a top-level comment.
    op.add_column(
        "comments",
        sa.Column(
            "parent_id",
            UUID(as_uuid=False),
            sa.ForeignKey("comments.id"),
            nullable=True,
        ),
    )
    # Denormalised, but safe: parent_id never changes after insert, so depth
    # cannot drift. Storing it means enforcing the cap is one comparison
    # rather than a recursive walk on every reply.
    op.add_column(
        "comments",
        sa.Column("depth", sa.SmallInteger, nullable=False, server_default="0"),
    )
    # Fetching a thread groups replies by parent.
    op.create_index("ix_comments_parent", "comments", ["parent_id"])

    # 'deleted' joins the existing set. Rewriting the constraint rather than
    # adding one, since a CHECK cannot be extended in place.
    op.drop_constraint("ck_comments_status", "comments", type_="check")
    op.create_check_constraint(
        "ck_comments_status",
        "comments",
        "status in ('visible','pending','hidden','removed','deleted')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_comments_status", "comments", type_="check")
    op.create_check_constraint(
        "ck_comments_status",
        "comments",
        "status in ('visible','pending','hidden','removed')",
    )
    op.drop_index("ix_comments_parent", table_name="comments")
    op.drop_column("comments", "depth")
    op.drop_column("comments", "parent_id")
