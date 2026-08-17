"""importance scoring inputs

Revision ID: 0018
Revises: 0017

Everything the importance formula reads, added in one place. The formula
itself lives in worker/importance.py; these are its four inputs plus the
column it writes.

The change in kind worth noting: corroboration used to be a BINARY FLOOR
here -- the feed showed stories with 2+ outlets, summaries needed 5+. Now it
is a CONTINUOUS WEIGHT, which is why `content_hash` suddenly matters. Under a
floor, five outlets running one identical wire story cleared the same bar
five independent newsrooms would; the error was capped at "included when it
should not have been". Under a weight, that same syndication inflates the
score every single time it is computed, and inflates it most for exactly the
wire stories least deserving of a brief. Collapsing by hash is a scoring
integrity fix, not deduplication for its own sake.

`content_hash` is deliberately NOT unique. The obvious reading of "dedupe
syndicated items" is a unique index, and that would be wrong: it would reject
the second outlet's copy at insert, destroying the evidence that a second
outlet ran it at all. Store every copy, collapse when counting.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0.5, not 1.0: the default is "an outlet we have not rated", which should
    # sit in the middle of the range rather than at the top of it. Seeding
    # real values is 0021.
    op.add_column(
        "outlets",
        sa.Column(
            "authority_weight",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
    )
    # The formula assumes this term is already 0-1 and does not normalize it,
    # so the constraint is what makes that assumption safe.
    op.create_check_constraint(
        "ck_outlets_authority_weight",
        "outlets",
        "authority_weight >= 0 and authority_weight <= 1",
    )

    op.add_column("articles", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("articles", sa.Column("author", sa.Text(), nullable=True))
    # Non-unique on purpose -- see the module docstring. This index serves the
    # count(distinct content_hash) in the scoring query, nothing else.
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])

    op.add_column(
        "stories",
        sa.Column(
            "importance_score", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
    )
    # Reporting speculation rather than confirmed fact. The generator is
    # required to name the outlet and mark it as reporting when this is true,
    # so it is a product requirement wearing a boolean.
    op.add_column(
        "stories",
        sa.Column("is_rumor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Resolved in code from team + date, never asked of the model: a
    # hallucinated game id would put fabricated numbers into a brief through
    # the one door that is supposed to be sealed.
    op.add_column(
        "stories",
        sa.Column(
            "linked_game_id",
            UUID(as_uuid=False),
            sa.ForeignKey("games.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "stories",
        sa.Column("importance_computed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Section selection reads this, ordered, on every brief run.
    op.create_index("ix_stories_importance", "stories", ["importance_score"])

    # Derived from the rank categorize.py already returns (1/(rank+1)) rather
    # than asked of the model as a number. Models are unreliable at scoring
    # their own confidence, and rank is information we are already being given
    # for free.
    op.add_column(
        "story_teams",
        sa.Column("relevance", sa.Float(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("story_teams", "relevance")
    op.drop_index("ix_stories_importance", table_name="stories")
    op.drop_column("stories", "importance_computed_at")
    op.drop_column("stories", "linked_game_id")
    op.drop_column("stories", "is_rumor")
    op.drop_column("stories", "importance_score")
    op.drop_index("ix_articles_content_hash", table_name="articles")
    op.drop_column("articles", "author")
    op.drop_column("articles", "content_hash")
    op.drop_constraint("ck_outlets_authority_weight", "outlets", type_="check")
    op.drop_column("outlets", "authority_weight")
