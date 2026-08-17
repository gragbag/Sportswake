"""stories.importance_peak

Revision ID: 0023
Revises: 0022

The major-story override asks "is this cluster in the top 3% of the last
thirty days?" -- and that question needs a population of comparable numbers.
`importance_score` is not one. It carries a recency term that decays with the
wall clock, so a story stops being rescored four days in and freezes near its
FLOOR, not its peak. Left alone, the thirty-day window fills with near-zero
frozen values, the 97th percentile sinks toward them, and the override starts
firing on ordinary stories -- the exact failure the percentile was chosen to
avoid, arriving quietly as the corpus ages.

Peak is the honest reading of "how big did this story get". It never decays,
so a story from three weeks ago is compared at its height against a story
from this morning at its height.

Backfilled from the current score: for anything recent that IS its peak, and
for anything old the best estimate available. It self-corrects on the next
run, since peak only ever moves up.
"""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column(
            "importance_peak", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.execute("update stories set importance_peak = importance_score")
    # The percentile query scans this over a 30-day window on every brief run.
    op.create_index("ix_stories_importance_peak", "stories", ["importance_peak"])


def downgrade() -> None:
    op.drop_index("ix_stories_importance_peak", table_name="stories")
    op.drop_column("stories", "importance_peak")
