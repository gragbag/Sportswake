"""teams and story_teams

Revision ID: 0013
Revises: 0012

Who a story is about. Separate from categories, which say what KIND of story
it is -- a Lakers trade is teams=[LAL, ...] and category=trades, and the
classifier returns both from one call. Collapsing them would lose "every
trade this week" to gain nothing.

Three kinds, same trick the general-news version used for countries: 30 team
codes are three characters, conferences and the league marker are longer, so
a code's length tells you its kind without reading `kind`.

LEAGUE is not a fallback for "could not tell". It means genuinely
league-wide -- CBA talks, expansion, media rights. A story about two teams
gets both team codes, and the classifier is told to prefer that.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_SCOPES = [
    ("LEAGUE", "League-wide", "league"),
    ("EAST", "Eastern Conference", "conference"),
    ("WEST", "Western Conference", "conference"),
]

# Codes are the ones every box score and outlet already uses, so the model
# has seen them constantly and needs no list in the prompt -- the same reason
# the general-news build could ask for ISO country codes.
_TEAMS = [
    # Eastern -- Atlantic
    ("BOS", "Boston Celtics"), ("BKN", "Brooklyn Nets"),
    ("NYK", "New York Knicks"), ("PHI", "Philadelphia 76ers"),
    ("TOR", "Toronto Raptors"),
    # Eastern -- Central
    ("CHI", "Chicago Bulls"), ("CLE", "Cleveland Cavaliers"),
    ("DET", "Detroit Pistons"), ("IND", "Indiana Pacers"),
    ("MIL", "Milwaukee Bucks"),
    # Eastern -- Southeast
    ("ATL", "Atlanta Hawks"), ("CHA", "Charlotte Hornets"),
    ("MIA", "Miami Heat"), ("ORL", "Orlando Magic"),
    ("WAS", "Washington Wizards"),
    # Western -- Northwest
    ("DEN", "Denver Nuggets"), ("MIN", "Minnesota Timberwolves"),
    ("OKC", "Oklahoma City Thunder"), ("POR", "Portland Trail Blazers"),
    ("UTA", "Utah Jazz"),
    # Western -- Pacific
    ("GSW", "Golden State Warriors"), ("LAC", "LA Clippers"),
    ("LAL", "Los Angeles Lakers"), ("PHX", "Phoenix Suns"),
    ("SAC", "Sacramento Kings"),
    # Western -- Southwest
    ("DAL", "Dallas Mavericks"), ("HOU", "Houston Rockets"),
    ("MEM", "Memphis Grizzlies"), ("NOP", "New Orleans Pelicans"),
    ("SAS", "San Antonio Spurs"),
]


def upgrade() -> None:
    op.create_table(
        "teams",
        # 8, not 3: conference and league codes share this table.
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        # 'team' | 'conference' | 'league'
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
    )

    op.create_table(
        "story_teams",
        # CASCADE, like story_categories: a tag is derived data that
        # merge_pass may delete without asking anyone. The tables holding
        # things a person made -- favorites, comments -- must never do that.
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "team_code", sa.String(8), sa.ForeignKey("teams.code"), primary_key=True
        ),
        sa.Column("rank", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # The PK leads with story_id, which serves "teams in this story". A team
    # tab asks the opposite question and needs the columns the other way.
    op.create_index("ix_story_teams_code", "story_teams", ["team_code", "story_id"])

    rows = [
        {"code": c, "name": n, "kind": k, "sort_order": i}
        for i, (c, n, k) in enumerate(_SCOPES, start=1)
    ] + [
        {"code": c, "name": n, "kind": "team", "sort_order": i}
        for i, (c, n) in enumerate(_TEAMS, start=len(_SCOPES) + 1)
    ]
    op.bulk_insert(
        sa.table(
            "teams",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("kind", sa.String),
            sa.column("sort_order", sa.SmallInteger),
        ),
        rows,
    )

    # Alembic-created tables do not inherit RLS, and Supabase grants anon full
    # DML on public by default -- so this is what actually keeps them locked.
    op.execute("alter table teams enable row level security")
    op.execute("alter table story_teams enable row level security")


def downgrade() -> None:
    op.drop_index("ix_story_teams_code", table_name="story_teams")
    op.drop_table("story_teams")
    op.drop_table("teams")
