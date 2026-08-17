"""seed authority_weight for the existing outlets

Revision ID: 0021
Revises: 0020

0018 added the column with a neutral 0.5 default. This gives the outlets that
already exist a real value, because they were inserted long before the column
did and sync_outlets will not revisit them.

Division of labour, matching how `name` already behaves in this system:
feeds.yaml seeds an outlet ON INSERT and never touches it again, so a weight
changed directly in the database stays changed. That is what makes the feed
list "configurable in the database" rather than configurable in a file that
requires a deploy -- and it is why this is a one-time backfill rather than
something sync_outlets reasserts every hour.

The scale is what the formula's max_source_authority term reads, and it is a
MAX across the story's outlets, not a mean. So a weight is really answering
"if this were the only outlet on the story, how much should that alone
count?" -- which is why a wire-service aggregator and a beat newspaper that
breaks its own news sit far apart even when they carry identical text.

These are starting values, not measurements. The honest way to set them is
against the eval set once briefs are running; until then they encode the
ordinary editorial distinction between reporting and repackaging.
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# Keyed on name rather than feed_url purely for readability. An outlet whose
# name does not match keeps the neutral 0.5 from 0018 -- degrading to
# "unrated" is the right failure here, and a wrong high weight would be worse
# than no weight at all.
_WEIGHTS = {
    # Originates reporting other outlets then cite.
    "ESPN NBA": 1.0,
    "LA Times Lakers": 0.85,
    # The transactions system of record -- narrow, but close to authoritative
    # on exactly the story type that clusters best here.
    "Hoops Rumors": 0.85,
    "CBS Sports NBA": 0.8,
    "Yahoo Sports NBA": 0.8,
    "Guardian NBA": 0.75,
    "RealGM Wiretap": 0.7,
    # Real newsroom, tabloid register.
    "NY Post NBA": 0.6,
    "Sporting News NBA": 0.6,
    # Authoritative within its own beat, which is not the NBA.
    "Eurohoops": 0.6,
    "SB Nation NBA": 0.6,
    "Sportando": 0.55,
    # Team sites: single-team by design and rarely first, but they confirm a
    # team story independently, which is the whole point of the source count.
    "Silver Screen and Roll": 0.5,
    "CelticsBlog": 0.5,
    "Golden State of Mind": 0.5,
    "Posting and Toasting": 0.5,
    "Liberty Ballers": 0.5,
    "Talkbasket": 0.45,
    # Repackages other outlets' reporting. Low weight is not a judgement on
    # accuracy -- it is that its presence adds little evidence a story is
    # real, which is the only question this number is asked.
    "Sportsnaut NBA": 0.4,
    "Yardbarker NBA": 0.35,
    "Fadeaway World": 0.3,
}


def upgrade() -> None:
    for name, weight in _WEIGHTS.items():
        op.execute(
            sa.text(
                "update outlets set authority_weight = :w where name = :n"
            ).bindparams(w=weight, n=name)
        )


def downgrade() -> None:
    # Back to the column default from 0018. Not a perfect inverse -- a weight
    # hand-tuned in the database after this ran is lost -- but a downgrade
    # that guessed at prior values would be worse.
    op.execute("update outlets set authority_weight = 0.5")
