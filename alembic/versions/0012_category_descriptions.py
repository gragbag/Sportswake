"""category descriptions, and us-politics becomes politics

Revision ID: 0012
Revises: 0011

Two fixes to one root cause. The prompt sent the model eight bare labels and
nothing else, so "Culture" meant whatever an 8B model decided it meant on each
call -- it filed a UK by-election there because the candidate wears a bin, and
a Kennedy Center board fight because the words name an arts venue. A category
with no written boundary gets matched on surface nouns.

The rename is the second half. 73% of this corpus comes from non-US outlets
and the four largest are Indian, British, British and Australian, so a
us-politics bucket left Indian, Australian and UK politics with nowhere to go
-- which is the other reason the by-election ended up in culture. One politics
category covering any country fits the corpus; a US/global split would make
the US a special case at 27% of it, and a global-politics slug would overlap
world closely enough that a small model coin-flips between them.

story_categories is cleared rather than migrated. category_slug has no ON
UPDATE CASCADE so the rename could not carry its rows anyway, and the new
descriptions change how borderline stories classify, so tags written under the
old prompt are not worth preserving. They are derived data: `make categorize`
regenerates them for one small-model call each.
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
    ("world", "World", "International affairs, conflict, diplomacy, disasters."),
    (
        "politics",
        "Politics",
        "Elections, parties, legislatures, government and public policy, in any country.",
    ),
    ("business", "Business & Economy", "Companies, markets, trade, jobs, the economy."),
    (
        "technology",
        "Technology",
        "Software, hardware, AI, telecoms, and the companies building them.",
    ),
    (
        "science-health",
        "Science & Health",
        "Research, space, climate science, medicine, public health.",
    ),
    (
        "crime-justice",
        "Crime & Justice",
        "Crimes, investigations, trials, courts, policing.",
    ),
    ("sports", "Sports", "Competition, athletes, clubs, results."),
    (
        "culture",
        "Culture",
        (
            "Film, TV, music, books, art, celebrity, media. Not politics that "
            "happens to involve an arts institution."
        ),
    ),
]


def upgrade() -> None:
    op.add_column("categories", sa.Column("description", sa.String(200), nullable=True))

    # Order matters: the FK on category_slug has no ON UPDATE CASCADE, so
    # nothing may reference us-politics when it is renamed.
    op.execute("delete from story_categories")
    op.execute("update categories set slug = 'politics' where slug = 'us-politics'")

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
    op.execute("update categories set slug = 'us-politics' where slug = 'politics'")
    op.execute("update categories set label = 'US Politics' where slug = 'us-politics'")
    op.drop_column("categories", "description")
