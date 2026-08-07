"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enabled now so milestone 3 does not require a schema change under load.
    # Nothing uses it yet.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "outlets",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("feed_url", sa.Text, nullable=False, unique=True),
        sa.Column("etag", sa.Text),
        sa.Column("last_modified", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "articles",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "outlet_id",
            UUID(as_uuid=False),
            sa.ForeignKey("outlets.id"),
            nullable=False,
        ),
        sa.Column("guid", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("lede", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("outlet_id", "guid", name="uq_articles_outlet_guid"),
    )
    op.create_index("ix_articles_published_at", "articles", ["published_at"])

    op.create_table(
        "fetch_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "outlet_id",
            UUID(as_uuid=False),
            sa.ForeignKey("outlets.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("payload_hash", sa.String(64)),
        sa.Column("payload_bytes", sa.Integer),
        sa.Column("items_seen", sa.Integer, server_default="0"),
        sa.Column("items_inserted", sa.Integer, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_fetch_runs_outlet_started", "fetch_runs", ["outlet_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_table("fetch_runs")
    op.drop_table("articles")
    op.drop_table("outlets")
