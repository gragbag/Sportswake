"""stories.summary_text, and backfill story_teams.relevance

Revision ID: 0022
Revises: 0021

Two small things the tagging stage needs.

`summary_text` is the 2-4 sentence prose summary, written by the same call
that already produces the title, subhead and bullets -- so it costs output
tokens, not an extra request.

Worth recording why it exists but is NOT fed to the brief generator: handing
a model finished prose invites it to lightly reword that prose, which is the
exact failure the editorial rules exist to prevent ("if the brief reads like
reworded headlines, the product has no reason to exist"). The generator gets
the BULLETS instead, because discrete facts force composition rather than
paraphrase. summary_text is stored for display surfaces and for anything that
wants a story in one paragraph without reading a whole section.

`relevance` arrived in 0018 with a 0 default. It is defined as 1/(rank+1),
which is pure arithmetic on a column we already have -- so every existing row
can be filled in right now with no model call and no re-tagging. Without this
backfill the 82 rows tagged before 0018 would sort last forever, because a
section orders its stories by relevance.
"""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("summary_text", sa.Text(), nullable=True))

    # rank 0 -> 1.0, rank 1 -> 0.5, rank 2 -> 0.333. Derived from the ordering
    # the classifier already returns rather than asked of it as a number:
    # models score their own confidence badly, and rank is free.
    op.execute("update story_teams set relevance = 1.0 / (rank + 1)")


def downgrade() -> None:
    op.execute("update story_teams set relevance = 0")
    op.drop_column("stories", "summary_text")
