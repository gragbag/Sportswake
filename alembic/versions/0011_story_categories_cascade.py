"""story_categories cascades when a story is deleted

Revision ID: 0011
Revises: 0010

merge_pass() folds two near-duplicate stories together: it re-points
story_members at the survivor, then deletes the absorbed row. It never learned
about the tables added after it was written, so the delete hit
story_categories_story_id_fkey and took down the hourly cluster step -- and
with it summarize, categorize and moderate, which run after it.

CASCADE is right for this table and WRONG for the other two that reference
stories. A category tag is derived data: worker.categorize regenerates it for
one small-model call, and it is stale the moment a merge changes the story's
member set anyway. favorites and comments are things a person made and can
never be silently deleted by a merge, so they stay NO ACTION and merge_pass
re-points them explicitly instead.

Fixing it at the constraint rather than in merge_pass covers every path that
deletes a story, present and future -- `cluster --reset` hits the same wall.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_FK = "story_categories_story_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK, "story_categories", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "story_categories",
        "stories",
        ["story_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_FK, "story_categories", type_="foreignkey")
    op.create_foreign_key(_FK, "story_categories", "stories", ["story_id"], ["id"])
