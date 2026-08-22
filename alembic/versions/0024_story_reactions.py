"""story_reactions

Revision ID: 0024
Revises: 0023

One reaction per (story, user) -- like, dislike, happy, sad, angry -- with
the composite key as the primary key rather than a surrogate id, the same
shape comment_votes already uses and for the same reason: the database
enforces "one per person" directly, and changing a reaction is an upsert on
the key rather than a read-modify-write.

Engagement only, not a personalization input. See StoryReaction's docstring
in common/models.py: a reaction tracks how a reader feels about the event,
not whether they want more of that team's coverage, and for a fan those can
point opposite ways. Favorites and follows remain what drives
recommendations.

The five values are a CHECK constraint rather than a reference table --
unlike categories or teams, nothing else ever needs to join against a
reaction, so a table buys a join for no reader anywhere.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_reactions",
        sa.Column(
            "story_id",
            UUID(as_uuid=False),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # No FK -- auth.users is Supabase's own schema and does not exist
        # in the local Docker database; see favorites for the same call.
        sa.Column("user_id", UUID(as_uuid=False), primary_key=True),
        sa.Column("reaction", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "reaction in ('like','dislike','happy','sad','angry')",
            name="ck_story_reactions_reaction",
        ),
    )

    # Alembic-created tables do not inherit RLS, and Supabase grants anon
    # full DML on public by default -- so this is what actually keeps it
    # locked.
    op.execute("alter table story_reactions enable row level security")


def downgrade() -> None:
    op.drop_table("story_reactions")
