"""comments and comment reports

Revision ID: 0006
Revises: 0005

One table serves both public comments and the private notes from milestone 6
-- they differ by `visibility`, so notes ship as a flag value rather than a
second subsystem.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_RLS_TABLES = ["comments", "comment_reports"]


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # Supabase auth.users id. No FK -- auth.users does not exist locally.
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id"),
            nullable=False,
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "visibility",
            sa.String(16),
            nullable=False,
            server_default="public",
        ),
        # Four states rather than a boolean so an exhausted moderation quota
        # can park a comment in 'pending' instead of choosing between
        # publishing it unchecked and losing it.
        sa.Column("status", sa.String(16), nullable=False, server_default="visible"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        # Cheap insurance against a client that ignores the API's own cap.
        sa.CheckConstraint(
            "length(body) between 1 and 4000", name="ck_comments_body_len"
        ),
        sa.CheckConstraint(
            "visibility in ('public','private')", name="ck_comments_visibility"
        ),
        sa.CheckConstraint(
            "status in ('visible','pending','hidden','removed')",
            name="ck_comments_status",
        ),
    )
    op.create_index("ix_comments_story_created", "comments", ["story_id", "created_at"])
    # Rate limiting counts rows over a trailing window on every insert, so
    # this index is load-bearing rather than an optimisation.
    op.create_index("ix_comments_user_created", "comments", ["user_id", "created_at"])

    op.create_table(
        "comment_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "comment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("comments.id"),
            nullable=False,
        ),
        sa.Column("reporter_id", UUID(as_uuid=False), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("comment_id", "reporter_id", name="uq_report_comment_user"),
    )
    op.create_index("ix_comment_reports_unresolved", "comment_reports", ["resolved_at"])

    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_comment_reports_unresolved", table_name="comment_reports")
    op.drop_table("comment_reports")
    op.drop_index("ix_comments_user_created", table_name="comments")
    op.drop_index("ix_comments_story_created", table_name="comments")
    op.drop_table("comments")
