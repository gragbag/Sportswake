"""brief_sections, user_teams

Revision ID: 0019
Revises: 0018

The output layer, and the cost model made physical.

Sections are generated PER TEAM, never per user: one league section plus one
per team that has qualifying news, so a slot costs at most 31 generations no
matter how many people read it or how many teams they follow. A user's brief
is assembled from these rows at read time. Ten thousand Lakers fans consume
one generation; following twelve teams consumes none.

`team_code` is NOT NULL, and league sections use the 'LEAGUE' code that 0013
already seeded. The obvious design is a nullable team_id with NULL meaning
league -- and it silently breaks the one guarantee this table exists to give,
because Postgres treats NULL as distinct from NULL in a UNIQUE constraint. A
nullable column would let unlimited duplicate league sections through while
appearing to forbid them, and the league section is the row most likely to be
generated twice, since every slot writes one.

That unique constraint is load-bearing beyond deduplication: "no row for this
slot" is how the scheduler knows a slot has not run, and how the reader knows
to fall back to an older one. Which is also why an empty league section still
writes a row carrying an honest one-line body, rather than writing nothing --
a missing row has to mean "not generated", never "generated, nothing to say".
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brief_sections",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # The ET calendar date the slot belongs to, not the UTC date it was
        # written on -- a night brief generated at 01:40 ET belongs to the day
        # whose games it recaps.
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(8), nullable=False),
        # Redundant with team_code == 'LEAGUE', kept because it is what the
        # reader groups on and a scope is cheaper to read than a sentinel.
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column(
            "team_code", sa.String(8), sa.ForeignKey("teams.code"), nullable=False
        ),
        sa.Column("body_md", sa.Text(), nullable=False),
        # Counted server-side from body_md. Never the model's self-report --
        # asking it to count its own words and then trusting the answer would
        # make the budget advisory.
        sa.Column("word_count", sa.Integer(), nullable=False),
        # Denormalized at write time so read-time ordering of a user's team
        # sections is one indexed query with no join back to stories. Same
        # trade as summarized_outlet_count.
        sa.Column(
            "max_importance", sa.Float(), nullable=False, server_default=sa.text("0")
        ),
        # Which stories this section actually used. The morning brief reads
        # the previous night's ids to avoid re-reporting what it already
        # covered, so this is not provenance decoration -- it is an input.
        sa.Column("cluster_ids", JSONB(), nullable=False),
        sa.Column("game_ids", JSONB(), nullable=True),
        # True when the p97 override lifted this section's word budget. Read
        # by the assembly cap, which a major story is allowed to exceed.
        sa.Column("is_major", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slot in ('morning', 'midday', 'night')", name="ck_brief_sections_slot"
        ),
        sa.CheckConstraint(
            "scope in ('league', 'team')", name="ck_brief_sections_scope"
        ),
        sa.UniqueConstraint(
            "slot_date", "slot", "team_code", name="uq_brief_sections_slot_team"
        ),
    )
    # The read path asks for one whole slot at a time.
    op.create_index("ix_brief_sections_slot", "brief_sections", ["slot_date", "slot"])

    op.create_table(
        "user_teams",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # No FK, exactly like favorites.user_id: auth.users lives in
        # Supabase's own schema, which Alembic does not manage.
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column(
            "team_code", sa.String(8), sa.ForeignKey("teams.code"), nullable=False
        ),
        sa.Column(
            "followed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # No cap on rows per user. Following twelve teams costs nothing to
        # generate, and the assembly cap -- not the follow list -- is what
        # keeps a brief readable.
        sa.UniqueConstraint("user_id", "team_code", name="uq_user_teams_user_team"),
    )
    op.create_index("ix_user_teams_user", "user_teams", ["user_id"])

    # The slot a reader sees is chosen from their browser's clock, so this is
    # not needed to render. It is here because a user who has told us their
    # timezone should not have to tell us again on a second device.
    op.add_column("profiles", sa.Column("timezone", sa.String(64), nullable=True))

    op.execute("alter table brief_sections enable row level security")
    op.execute("alter table user_teams enable row level security")


def downgrade() -> None:
    op.drop_column("profiles", "timezone")
    op.drop_index("ix_user_teams_user", table_name="user_teams")
    op.drop_table("user_teams")
    op.drop_index("ix_brief_sections_slot", table_name="brief_sections")
    op.drop_table("brief_sections")
