"""outlets.active -- feeds.yaml can retire a feed

Revision ID: 0016
Revises: 0015

Removing an entry from feeds.yaml never stopped ingest fetching it:
sync_outlets inserted the yaml entries but returned every outlet row in the
database, so a retired feed kept being fetched off its old row forever.
Harmless while the roster only ever grew; wrong the first time a feed was
replaced by a scoped variant (Sporting News -> Sporting News NBA) and the
all-sport original kept ingesting beside its replacement.

active means "fetch this", not "this exists". Articles keep their outlet
row either way, so retirement never touches history. No backfill: the very
next sync_outlets sets every row from yaml membership.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("outlets", "active")
