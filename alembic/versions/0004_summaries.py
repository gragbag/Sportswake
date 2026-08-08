"""story summary columns

Revision ID: 0004
Revises: 0003

Every column is nullable on purpose: unsummarized is the normal state (no
API key, budget exhausted, model returned garbage), so nothing downstream
may ever require these. No backfill needed -- existing rows are simply
"not summarized yet".
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Generated headline. The seed-article headline stays in stories.title
    # as provenance; the app prefers this one when present.
    op.add_column("stories", sa.Column("summary_title", sa.Text))
    # One line on why it matters / what happens next -- not a restatement.
    op.add_column("stories", sa.Column("summary_subhead", sa.Text))
    op.add_column("stories", sa.Column("summary_bullets", JSONB))
    # Only names that appear verbatim in the input text survive validation.
    op.add_column("stories", sa.Column("summary_people", JSONB))
    # Which model wrote it. Groq rotates its lineup; when output quality
    # shifts, this column says whether the model changed underneath us.
    op.add_column("stories", sa.Column("summary_model", sa.Text))
    op.add_column("stories", sa.Column("summarized_at", sa.DateTime(timezone=True)))
    # Distinct outlets at summary time. Regen fires only when the current
    # count reaches this * SUMMARY_REGEN_GROWTH, so one new outlet does not
    # burn a metered call.
    op.add_column("stories", sa.Column("summarized_outlet_count", sa.Integer))


def downgrade() -> None:
    op.drop_column("stories", "summarized_outlet_count")
    op.drop_column("stories", "summarized_at")
    op.drop_column("stories", "summary_model")
    op.drop_column("stories", "summary_people")
    op.drop_column("stories", "summary_bullets")
    op.drop_column("stories", "summary_subhead")
    op.drop_column("stories", "summary_title")
