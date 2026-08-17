"""games, box_lines, score_runs -- the structured layer

Revision ID: 0017
Revises: 0016

The brief product draws on two sources that are kept strictly apart: RSS
supplies narrative and reporting, this table supplies every number. A brief
that says a player scored 38 read that from here, never from a headline.
The separation is the whole defence against stale or hallucinated stats
laundered through a summary, so it is enforced by having nowhere else for a
score to come from.

Three things about the upstream API that the column choices encode:

`final_at` is OURS, not theirs. The provider has no completion timestamp --
`status` is a display string that walks "7:00 pm ET" -> "1st Qtr" -> ... ->
"Final". So final_at is stamped by the poller the first time it observes a
final, and never rewritten. The night brief waits 30 minutes from that
observation, which is the only clock we actually have.

`game_date_et` is the TIP-OFF date in Eastern, computed here rather than
taken from the provider's own date field. A 10:30pm ET tip that ends at
1:15am is still tonight's game, and "tonight's slate" is the question every
night-brief query asks.

`postponed` is kept beside `status` rather than folded into it because the
provider reports them separately, and the night trigger needs to tell "not
finished yet" from "will never finish" -- a postponement that counted as
pending would hang the brief exactly like a stuck live game.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Conference and division for the 30 clubs. The groupings were already in
# 0013's seed list as comments; this promotes them to columns so a section
# can be built for a conference without hardcoding thirty codes somewhere
# else. Scope rows (LEAGUE/EAST/WEST) stay null -- they are not IN a
# conference, they ARE one.
_ALIGNMENT = {
    "Atlantic": ("East", ["BOS", "BKN", "NYK", "PHI", "TOR"]),
    "Central": ("East", ["CHI", "CLE", "DET", "IND", "MIL"]),
    "Southeast": ("East", ["ATL", "CHA", "MIA", "ORL", "WAS"]),
    "Northwest": ("West", ["DEN", "MIN", "OKC", "POR", "UTA"]),
    "Pacific": ("West", ["GSW", "LAC", "LAL", "PHX", "SAC"]),
    "Southwest": ("West", ["DAL", "HOU", "MEM", "NOP", "SAS"]),
}


def upgrade() -> None:
    op.add_column("teams", sa.Column("conference", sa.String(4), nullable=True))
    op.add_column("teams", sa.Column("division", sa.String(16), nullable=True))
    # Filled by the first scores sync, matching on abbreviation. Nullable and
    # unique rather than seeded: hardcoding another provider's surrogate ids
    # into a migration means a re-seed on their side becomes a migration on
    # ours.
    op.add_column("teams", sa.Column("bdl_team_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_teams_bdl_team_id", "teams", ["bdl_team_id"])

    # One statement per code rather than one per division with an array bind:
    # a list parameter cannot be rendered by `alembic upgrade --sql`, and
    # being able to review a migration offline is worth thirty tiny UPDATEs
    # that run once.
    for division, (conference, codes) in _ALIGNMENT.items():
        for code in codes:
            op.execute(
                sa.text(
                    "update teams set conference = :conf, division = :div "
                    "where code = :code"
                ).bindparams(conf=conference, div=division, code=code)
            )

    op.create_table(
        "games",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # The provider's id is the dedup key -- stable across re-polls of the
        # same game, which is the entire reason we re-poll.
        sa.Column("bdl_game_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("game_date_et", sa.Date(), nullable=False),
        sa.Column("tipoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "home_team_code", sa.String(8), sa.ForeignKey("teams.code"), nullable=False
        ),
        sa.Column(
            "away_team_code", sa.String(8), sa.ForeignKey("teams.code"), nullable=False
        ),
        # Normalized by the poller to scheduled | live | final, so the due
        # check never parses a display string. Postponement is the column
        # below, not a status.
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("postponed", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Null until the game has actually been played.
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        # Written once, on the first poll that sees a final. See the module
        # docstring -- this is our observation, not the provider's.
        sa.Column("final_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("polled_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_games_date_et", "games", ["game_date_et"])

    op.create_table(
        "box_lines",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # CASCADE: a box line is derived data with no meaning apart from its
        # game, unlike anything a person made.
        sa.Column(
            "game_id",
            UUID(as_uuid=False),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bdl_player_id", sa.Integer(), nullable=False),
        sa.Column("player_name", sa.String(100), nullable=False),
        sa.Column(
            "team_code", sa.String(8), sa.ForeignKey("teams.code"), nullable=False
        ),
        # Stored as the provider sends it -- "34:12" or "34". Parsing to an
        # integer here would throw away the seconds for no gain; the brief
        # quotes minutes, it does not do arithmetic on them.
        sa.Column("min", sa.String(8), nullable=True),
        sa.Column("pts", sa.SmallInteger(), nullable=True),
        sa.Column("reb", sa.SmallInteger(), nullable=True),
        sa.Column("ast", sa.SmallInteger(), nullable=True),
        sa.Column("stl", sa.SmallInteger(), nullable=True),
        sa.Column("blk", sa.SmallInteger(), nullable=True),
        # The provider calls this `turnover`; mapped on read.
        sa.Column("tov", sa.SmallInteger(), nullable=True),
        sa.Column("plus_minus", sa.SmallInteger(), nullable=True),
        sa.UniqueConstraint(
            "game_id", "bdl_player_id", name="uq_box_lines_game_player"
        ),
    )
    op.create_index("ix_box_lines_game", "box_lines", ["game_id"])

    # Mirrors fetch_runs, for the same reason it exists: a poller that stops
    # is invisible until someone notices the data is stale, and the night
    # brief's trigger depends on this data being current.
    op.create_table(
        "score_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),  # ok | error
        sa.Column("games_seen", sa.Integer(), nullable=True),
        sa.Column("box_lines_written", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_score_runs_started", "score_runs", ["started_at"])

    op.execute("alter table games enable row level security")
    op.execute("alter table box_lines enable row level security")
    op.execute("alter table score_runs enable row level security")


def downgrade() -> None:
    op.drop_index("ix_score_runs_started", table_name="score_runs")
    op.drop_table("score_runs")
    op.drop_index("ix_box_lines_game", table_name="box_lines")
    op.drop_table("box_lines")
    op.drop_index("ix_games_date_et", table_name="games")
    op.drop_table("games")
    op.drop_constraint("uq_teams_bdl_team_id", "teams", type_="unique")
    op.drop_column("teams", "bdl_team_id")
    op.drop_column("teams", "division")
    op.drop_column("teams", "conference")
