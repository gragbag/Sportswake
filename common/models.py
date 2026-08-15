"""Shared schema. Both the worker and the app import from here.

Migrations are owned by Alembic and by the worker side only. The app never
alters schema.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import EMBEDDING_DIM  # Also loads the .env variables


class Base(DeclarativeBase):
    """Declarative base.

    Nullability lives in the annotation now, not in a nullable= argument:
    Mapped[X] is NOT NULL, Mapped[X | None] is nullable. Alembic compares
    these against alembic/versions/, so an annotation that disagrees with the
    migration surfaces as drift in `alembic check`.
    """


def _uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Outlet(Base):
    __tablename__ = "outlets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(200))
    feed_url: Mapped[str] = mapped_column(Text, unique=True)

    # Conditional-request state. Sending these back means unchanged feeds
    # return a cheap 304 instead of the full body.
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    outlet_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("outlets.id")
    )

    # The outlet's own stable identifier for the item. More reliable than the
    # URL, which picks up tracking parameters and sometimes changes.
    guid: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    headline: Mapped[str] = mapped_column(Text)
    lede: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(EMBEDDING_DIM))

    # Dedup key. Reruns and overlapping fetch windows are safe because inserts
    # use ON CONFLICT DO NOTHING against this constraint.
    __table_args__ = (
        UniqueConstraint("outlet_id", "guid", name="uq_articles_outlet_guid"),
        Index("ix_articles_published_at", "published_at"),
    )


class FetchRun(Base):
    """One row per attempted fetch, successful or not.

    This table is what the /status page reads. A run that fails still gets a
    row -- silence is the failure mode we are trying to make visible.
    """

    __tablename__ = "fetch_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    outlet_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("outlets.id")
    )

    status: Mapped[str] = mapped_column(String(20))  # ok | not_modified | error
    http_status: Mapped[int | None] = mapped_column(Integer)
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    payload_bytes: Mapped[int | None] = mapped_column(Integer)
    items_seen: Mapped[int | None] = mapped_column(Integer, default=0)
    items_inserted: Mapped[int | None] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_fetch_runs_outlet_started", "outlet_id", "started_at"),)


class Story(Base):
    """A cluster of articles about one event.

    last_activity_at is the newest coalesce(published_at, first_seen_at) among
    members. It does double duty: it filters the candidate window, and it is
    the timestamp the Gaussian time decay measures Δt against -- which is what
    lets a live story keep accepting articles while a dormant one stops.
    """

    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    title: Mapped[str | None] = mapped_column(Text)
    centroid: Mapped[list[float]] = mapped_column(HALFVEC(EMBEDDING_DIM))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Generated summary (milestone 5). All nullable: unsummarized is the
    # normal state, not an error, and `title` above keeps the seed-article
    # headline as provenance -- the summary never overwrites it.
    summary_title: Mapped[str | None] = mapped_column(Text)
    # One line on why it matters / what happens next. Not a restatement.
    summary_subhead: Mapped[str | None] = mapped_column(Text)
    summary_bullets: Mapped[list[str] | None] = mapped_column(JSONB)
    # Names validated to appear verbatim in the input text before storing.
    summary_people: Mapped[list[str] | None] = mapped_column(JSONB)
    summary_model: Mapped[str | None] = mapped_column(Text)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Distinct outlets at summary time. The regen rule compares the current
    # count against this * SUMMARY_REGEN_GROWTH.
    summarized_outlet_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_stories_last_activity", "last_activity_at"),)


class StoryMember(Base):
    """One row per membership decision.

    Append-only: rows are inserted, never updated or deleted, so clustering can
    be replayed at a different threshold and diffed against the current state.
    """

    __tablename__ = "story_members"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    story_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("stories.id"))
    article_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("articles.id"), unique=True
    )
    # Raw cosine, not the time-decayed score -- see the migration comment.
    similarity: Mapped[float] = mapped_column(Float)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_story_members_story", "story_id"),)


class Favorite(Base):
    """A story a user saved.

    user_id holds the Supabase auth.users id (the JWT's `sub`) but has NO
    foreign key to it, deliberately. auth.users lives in Supabase's own
    schema and does not exist in the local Docker database, so a real FK
    would make `make db-migrate LOCAL=1` fail and split the schema in two.
    The cost is orphan rows if an account is deleted, which is cheap to
    sweep and cheaper than two divergent schemas.
    """

    __tablename__ = "favorites"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    story_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("stories.id"))
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Favoriting twice is the same as favoriting once, so the constraint lets
    # the insert be ON CONFLICT DO NOTHING -- same idempotency rule the
    # article inserts follow.
    __table_args__ = (
        UniqueConstraint("user_id", "story_id", name="uq_favorites_user_story"),
        Index("ix_favorites_user_saved", "user_id", "saved_at"),
    )


class Profile(Base):
    """A user who has chosen a username.

    Deliberately NOT a row per account. Everyone gets a stable handle derived
    from their user id, so this table holds only the people who picked
    something else -- which means no backfill, no row to create at signup,
    and nothing reserved during email verification.

    Comments store user_id and join here at read time, so a rename shows up
    everywhere at once rather than needing every old row rewritten.
    """

    __tablename__ = "profiles"

    # The Supabase auth.users id (JWT `sub`). No FK -- auth.users is
    # Supabase's own schema and does not exist in the local database.
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    # Null means "still using the derived handle".
    username: Mapped[str | None] = mapped_column(String(20))
    # Drives the rename cooldown. Renaming frees the old handle for anyone
    # else, so rapid renames are an identity-swap tool; the cooldown makes
    # that impractical without forbidding renames outright.
    username_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Opt-out, not opt-in: comments are already public on the story page, so
    # hiding the aggregated view is a privacy preference rather than a
    # default. Hiding does not unpublish anything.
    hide_comment_history: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Declared here as well as in the migration, or `alembic check` sees an
    # index the models do not know about and proposes dropping it -- the
    # same drift that bit the stories indexes.
    __table_args__ = (
        Index(
            "ix_profiles_username_lower",
            text("lower(username)"),
            unique=True,
        ),
    )


class Category(Base):
    """A news category. Reference data, seeded by the migration.

    The slug is the primary key rather than a surrogate integer, so
    story_categories carries a readable value and filtering a tab never has
    to join this table at all -- most of the speed advantage of an array
    column, without giving up the ability to add a category with an INSERT
    instead of a migration.
    """

    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    # Goes into the classifier prompt, which is the only thing that reads it.
    # A bare label left "Culture" meaning whatever the model guessed per call,
    # so this is load-bearing rather than documentation.
    description: Mapped[str] = mapped_column(String(200))
    # Tab order. Data rather than code, so reordering is an UPDATE.
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class StoryCategory(Base):
    """Which categories a story belongs to. At most two, enforced in code.

    Composite primary key: a story cannot hold the same category twice, and
    the database says so rather than the application remembering to.
    """

    __tablename__ = "story_categories"

    # CASCADE, unlike favorites and comments: a tag is derived data that
    # worker.categorize regenerates, so a merge may delete it silently. The
    # tables holding things a person made must never do that.
    story_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_slug: Mapped[str] = mapped_column(
        String(32), ForeignKey("categories.slug"), primary_key=True
    )
    # 0 is the primary category -- the one shown when there is room for one.
    rank: Mapped[int] = mapped_column(SmallInteger, default=0)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # The tab query filters on the slug and joins back to stories, so the
    # slug has to lead. The PK index leads with story_id, which serves the
    # opposite direction.
    __table_args__ = (Index("ix_story_categories_slug", "category_slug", "story_id"),)


class Place(Base):
    """Where a story happens. Reference data, seeded by the migration.

    Holds three kinds in one table -- 'country', 'region' and 'global' -- so
    a story that spans a continent still gets a place rather than falling
    through to nothing. Region codes are longer than two characters, so a
    code's length distinguishes it from an ISO 3166-1 alpha-2 country
    without reading `kind`.

    The country list is curated rather than the full ISO 249. Adding one is
    an INSERT, not a migration, because code is the primary key.
    """

    __tablename__ = "places"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(8))
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class StoryPlace(Base):
    """Where a story happens. Same shape as StoryCategory, same reasons.

    Separate from story_categories rather than one polymorphic tag table:
    the two are validated differently -- categories against a list the model
    is shown, places against one it is not -- and a tab query for either
    should never have to filter out the other kind.
    """

    __tablename__ = "story_places"

    story_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    place_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("places.code"), primary_key=True
    )
    # 0 is the primary place -- where the story mostly happens.
    rank: Mapped[int] = mapped_column(SmallInteger, default=0)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Mirrors ix_story_categories_slug: the PK leads with story_id, so
    # "every story in India" needs the columns the other way round.
    __table_args__ = (Index("ix_story_places_code", "place_code", "story_id"),)


class Comment(Base):
    """A user's writing about a story.

    One table for two features, per the design note: a private note is this
    row with visibility='private', a public comment is visibility='public'.
    Shipping notes later is a flag value, not a new subsystem.

    user_id carries no FK to auth.users for the same reason favorites does
    not -- that table is Supabase's and absent locally.
    """

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    story_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("stories.id"))
    # Null for a top-level comment. Never changes after insert, which is why
    # depth below can be stored rather than walked.
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("comments.id")
    )
    depth: Mapped[int] = mapped_column(SmallInteger, default=0)
    body: Mapped[str] = mapped_column(Text)

    # 'public' | 'private'. Private rows are the milestone-6 note.
    visibility: Mapped[str] = mapped_column(String(16), default="public")
    # 'visible' | 'pending' | 'hidden' | 'removed' | 'deleted'. Not a
    # boolean, so an exhausted moderation quota can hold a comment for
    # review instead of forcing a choice between publishing it unchecked and
    # dropping it -- and so author deletion ('deleted') stays distinct from
    # moderation ('removed'). Rows are never actually deleted: appeals,
    # repeat-offender detection and orphaned replies all need them.
    status: Mapped[str] = mapped_column(String(16), default="visible")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Reading a thread.
        Index("ix_comments_story_created", "story_id", "created_at"),
        Index("ix_comments_parent", "parent_id"),
        # Rate limiting: "how many has this user posted since X". Must be
        # indexed -- it runs before every insert, and an unindexed count over
        # a growing table is the slowest thing in the request path.
        Index("ix_comments_user_created", "user_id", "created_at"),
    )


class CommentVote(Base):
    """One person's vote on one comment.

    Composite primary key rather than a surrogate id: one vote per person
    per comment is the rule, and making it the key means the database
    enforces it and changing your vote is an upsert rather than a
    read-modify-write.

    Stored as +1/-1 so the net score is a sum, while ups and downs stay
    separately countable -- which is what a confidence-interval sort would
    need if raw score ever proves too naive.
    """

    __tablename__ = "comment_votes"

    comment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("comments.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    # SmallInteger to match the migration -- a plain Integer here reads as
    # drift to `alembic check`.
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Scoring a thread groups by comment_id, so that side of the key needs
    # to lead. The PK index already does this, but naming it makes the
    # read path explicit.
    __table_args__ = (Index("ix_comment_votes_comment", "comment_id"),)


class CommentReport(Base):
    """A user flagging a comment.

    Exists from the start even though the report button comes later: a
    moderation queue you cannot populate is not a moderation queue, and
    adding the table now keeps the button a UI change.
    """

    __tablename__ = "comment_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    comment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("comments.id")
    )
    reporter_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # One report per person per comment; a second is a no-op, not a
        # louder signal.
        UniqueConstraint("comment_id", "reporter_id", name="uq_report_comment_user"),
        Index("ix_comment_reports_unresolved", "resolved_at"),
    )


def make_engine(url: str | None = None, serverless: bool = False):
    """Build an engine.

    serverless=True disables pooling on our side, which is what you want when
    the app runs as short-lived instances behind Supabase's transaction-mode
    pooler. The worker is a long-lived process and should pool normally.
    """
    url = url or os.environ["DATABASE_URL"]
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if serverless:
        from sqlalchemy.pool import NullPool

        kwargs = {"poolclass": NullPool}
    return create_engine(url, **kwargs)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
