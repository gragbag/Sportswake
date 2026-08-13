"""profiles

Revision ID: 0007
Revises: 0006

One row per user who has CHOSEN a username, not one per account. Everyone
else renders a handle derived from their user id, so signup writes nothing
here and no name is reserved while an email sits unverified.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        # Supabase auth.users id. No FK: that table lives in Supabase's own
        # schema and is absent from the local database.
        sa.Column("user_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("username", sa.String(20)),
        sa.Column("username_changed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Backstop against a client that skips the API's own validation.
        sa.CheckConstraint(
            "username is null or username ~ '^[a-zA-Z0-9_]{3,20}$'",
            name="ck_profiles_username_format",
        ),
    )
    # Functional unique index rather than a citext column: no extension to
    # install, identical behaviour on Docker and Supabase, and it makes
    # "Julian" and "julian" the same name -- which they must be, or the
    # handle stops identifying anyone.
    op.execute(
        "CREATE UNIQUE INDEX ix_profiles_username_lower ON profiles (lower(username))"
    )

    op.execute("ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_profiles_username_lower", table_name="profiles")
    op.drop_table("profiles")
