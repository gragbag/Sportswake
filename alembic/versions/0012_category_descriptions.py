"""category descriptions

Revision ID: 0012
Revises: 0011

A bare label is not enough for a small model. In the general-news build this
table shipped eight one-word labels and nothing else, and "Culture" came to
mean whatever the model guessed per call -- it filed a UK by-election there
because the candidate wears a bin costume. A category with no written
boundary gets matched on surface nouns.

Basketball has the same trap in a different shape. "Trades" and "Free Agency"
are one blurred idea to a model that has not been told a sign-and-trade is a
trade, and almost every trade story mentions injuries. So each description
below says what the category EXCLUDES, not just what it covers.

story_categories is cleared because the descriptions change how borderline
stories classify; tags written before them are not worth keeping. They are
derived data -- `make categorize` regenerates each for one small-model call.
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# One line each, written as boundaries rather than definitions -- the useful
# part of a description here is what it EXCLUDES. The culture line ends the
# way it does because of the Kennedy Center case specifically.
_DESCRIPTIONS = [
    (
        "games",
        "Games",
        "Results, recaps, series, standings and previews of scheduled games.",
    ),
    (
        "trades",
        "Trades",
        (
            "Completed or reported trades, buyouts and waivers. A sign-and-trade "
            "is a trade. Rumours count."
        ),
    ),
    (
        "free-agency",
        "Free Agency",
        "Signings, extensions, options and contract disputes. Not trades.",
    ),
    (
        "injuries",
        "Injuries",
        (
            "Injury, recovery, surgery, load management. Only when the injury "
            "is the story, not when a game recap mentions one."
        ),
    ),
    (
        "draft",
        "Draft",
        "Prospects, lottery, draft night, two-way and G League call-ups.",
    ),
    (
        "business",
        "Business",
        "Ownership, the CBA, media rights, expansion, arenas, sponsorship.",
    ),
    (
        "off-court",
        "Off Court",
        (
            "Legal matters, league discipline, personal news. Not on-court "
            "incidents during a game."
        ),
    ),
]


def upgrade() -> None:
    op.add_column("categories", sa.Column("description", sa.String(200), nullable=True))

    op.execute("delete from story_categories")

    for slug, label, description in _DESCRIPTIONS:
        op.execute(
            sa.text(
                "update categories set label = :label, description = :description "
                "where slug = :slug"
            ).bindparams(slug=slug, label=label, description=description)
        )

    # Only enforced after the seed rows are filled in; a category with no
    # description would silently weaken the prompt for every story.
    op.alter_column("categories", "description", nullable=False)


def downgrade() -> None:
    op.execute("delete from story_categories")
    op.drop_column("categories", "description")
