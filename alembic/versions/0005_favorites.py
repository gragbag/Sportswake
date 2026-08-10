"""favorites

Revision ID: 0005
Revises: 0004

Also enables row-level security, which the earlier tables did not do and had
to be fixed by hand: Supabase grants `anon` full DML on `public` by default
and treats RLS as the gate, so an Alembic-created table is world-writable via
PostgREST until RLS is on. Every new table gets it in the migration from now
on so the setting lives in schema history rather than in someone's memory.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Local Docker has no `anon` role, so the grant/RLS statements are Supabase
# specific. RLS itself is harmless on plain Postgres -- the owner bypasses it
# -- so the same migration runs cleanly in both places.
_RLS_TABLES = ["favorites"]


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # Supabase auth.users id, from the JWT's `sub`. No FK on purpose:
        # auth.users does not exist in the local database, and a cross-schema
        # FK would make local migrations fail.
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id"),
            nullable=False,
        ),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Lets the insert be ON CONFLICT DO NOTHING, so a double-click is a
        # no-op rather than a duplicate row.
        sa.UniqueConstraint("user_id", "story_id", name="uq_favorites_user_story"),
    )
    # Covers "this user's favorites, newest first" -- the only read path.
    op.create_index("ix_favorites_user_saved", "favorites", ["user_id", "saved_at"])

    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_favorites_user_saved", table_name="favorites")
    op.drop_table("favorites")
