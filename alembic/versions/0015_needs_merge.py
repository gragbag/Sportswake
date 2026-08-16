"""merge bookkeeping: stories.needs_merge

Revision ID: 0015
Revises: 0014

merge_pass used to SELECT every centroid every hour and rescore every pair in
NumPy -- ~3 KB of vector-as-text per story per run, which at 15k stories was
roughly 50 MB an hour, most of Supabase's monthly egress budget on its own.
The cosines now compute inside Postgres, and this flag is the other half of
the fix: a pair can only score differently than last pass if a side's centroid
changed, so only flagged stories are scored at all.

TRUE by default: a freshly seeded story, or one whose centroid was just
recomputed, is exactly what the next pass must look at.

Existing rows are backfilled to FALSE rather than left at the default. Every
pair among them was already scored by the old all-pairs code on the previous
hourly run, so flagging the whole corpus would spend the first pass -- dirty
times everything, minutes of shared CPU -- re-reaching verdicts the old code
had already reached. Raw cosine gates merging, so those verdicts do not age.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column(
            "needs_merge", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.execute("update stories set needs_merge = false")


def downgrade() -> None:
    op.drop_column("stories", "needs_merge")
