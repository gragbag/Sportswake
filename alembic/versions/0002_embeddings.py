"""Embedding schema

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("embedding", HALFVEC(384)))


def downgrade() -> None:
    op.drop_column("articles", "embedding")
