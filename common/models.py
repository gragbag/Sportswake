"""Shared schema. Both the worker and the app import from here.

Migrations are owned by Alembic and by the worker side only. The app never
alters schema.
"""

import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
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

    # "Fetch this", not "this exists". sync_outlets keeps it aligned with
    # feeds.yaml membership, so removing a yaml entry retires the feed while
    # its articles keep their outlet row and history survives.
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # How much this outlet alone vouches for a story. Read by the importance
    # formula as a MAX across the story's outlets, so it answers "if this were
    # the only source, how much should that count?" -- which is why a wire
    # aggregator and a paper that breaks its own news sit far apart even when
    # they carry identical text. Seeded on insert, then owned by the database:
    # sync_outlets never reasserts it, exactly as it never renames an outlet.
    authority_weight: Mapped[float] = mapped_column(Float, default=0.5)

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

    # When this article happened, as opposed to what the feed claimed. Every
    # query that orders or groups by time should use THIS, not published_at:
    # it is the one place the rule lives, and it was previously copied into
    # eleven separate coalesce() expressions that could drift apart.
    #
    # Generated, so it cannot disagree with its inputs, and so published_at
    # stays exactly what the outlet published. It currently repairs only the
    # impossible -- a missing date, or one after we fetched the item. A date
    # weeks BEFORE we saw it is left alone on purpose: that is either a
    # republished evergreen or an item we were late to fetch, and no rule
    # here can tell those apart.
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        Computed(
            "case when published_at is null then first_seen_at "
            "when published_at > first_seen_at then first_seen_at "
            "else published_at end",
            persisted=True,
        ),
    )

    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(EMBEDDING_DIM))

    # sha256 of the normalized headline+lede. Identifies the SAME TEXT running
    # at several outlets -- wire copy -- which the importance formula collapses
    # so nine reprints of one AP story do not read as nine newsrooms.
    #
    # Deliberately not unique: rejecting the second outlet's copy would destroy
    # the evidence that a second outlet ran it, which is the very thing being
    # measured. Store every copy, collapse when counting.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    author: Mapped[str | None] = mapped_column(Text)

    # Dedup key. Reruns and overlapping fetch windows are safe because inserts
    # use ON CONFLICT DO NOTHING against this constraint.
    __table_args__ = (
        UniqueConstraint("outlet_id", "guid", name="uq_articles_outlet_guid"),
        Index("ix_articles_published_at", "published_at"),
        # Ordering by time is the most common thing done to this table, and
        # every one of those queries now reads effective_at, not published_at.
        Index("ix_articles_effective_at", "effective_at"),
        Index("ix_articles_content_hash", "content_hash"),
        # Declared here as well as in 0020, or `alembic check` sees an index
        # the models do not know about and proposes dropping it.
        Index(
            "ix_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
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
    # Set on seed and on every centroid recompute, cleared once merge_pass
    # has scored the story against its window. Only a pair with a changed
    # side can score differently than it did last pass, so only those pairs
    # are scored -- this flag is what keeps the daily merge from re-reading
    # the whole corpus.
    needs_merge: Mapped[bool] = mapped_column(Boolean, default=True)

    # Generated summary (milestone 5). All nullable: unsummarized is the
    # normal state, not an error, and `title` above keeps the seed-article
    # headline as provenance -- the summary never overwrites it.
    summary_title: Mapped[str | None] = mapped_column(Text)
    # One line on why it matters / what happens next. Not a restatement.
    summary_subhead: Mapped[str | None] = mapped_column(Text)
    summary_bullets: Mapped[list[str] | None] = mapped_column(JSONB)
    # Two to four sentences of prose, from the same call as the bullets.
    # Deliberately NOT given to the brief generator: handing a model finished
    # prose invites rewording it, and the bullets force composition instead.
    summary_text: Mapped[str | None] = mapped_column(Text)
    # Names validated to appear verbatim in the input text before storing.
    summary_people: Mapped[list[str] | None] = mapped_column(JSONB)
    summary_model: Mapped[str | None] = mapped_column(Text)
    summarized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Distinct outlets at summary time. The regen rule compares the current
    # count against this * SUMMARY_REGEN_GROWTH.
    summarized_outlet_count: Mapped[int | None] = mapped_column(Integer)

    # The same three questions for categories that the two columns above ask
    # for summaries, plus one they do not need. NULL categorized_at means no
    # successful tagging yet; categorized_outlet_count is set on failures too,
    # so a story the model could not place can be reconsidered once it grows
    # rather than being written off forever.
    categorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    categorized_outlet_count: Mapped[int | None] = mapped_column(Integer)
    # Consecutive attempts that produced nothing usable. Without a bound these
    # stories return to the FRONT of the queue every run, because it is
    # ordered by outlet count -- so N hopeless stories cost N slots forever.
    category_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0", default=0
    )

    # What decides whether a story is worth a brief at all, and how much room
    # it earns. Computed arithmetic, never an LLM judgement -- a model asked
    # how important its own story is will inflate.
    importance_score: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0", default=0.0
    )
    # Speculation rather than confirmed fact. The generator must name the
    # outlet and mark it as reporting when this is true.
    is_rumor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # Resolved from team + ET date in code, never asked of the model: an
    # invented game id would put fabricated numbers into a brief through the
    # one door that is meant to be sealed.
    linked_game_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("games.id")
    )
    # Not a dirty flag, unlike needs_merge. Recency decays with the clock and
    # no write occurs, so this records when the arithmetic last ran rather
    # than whether it is owed.
    importance_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # The highest importance this story ever reached. Never decays, so it is
    # the only column the major-story percentile can honestly be drawn from:
    # importance_score freezes near its FLOOR once a story ages out of the
    # rescoring window, which would sink the 97th percentile toward zero as
    # the corpus grows and make the override fire on everything.
    importance_peak: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0", default=0.0
    )

    __table_args__ = (
        Index("ix_stories_last_activity", "last_activity_at"),
        Index("ix_stories_importance", "importance_score"),
        Index("ix_stories_importance_peak", "importance_peak"),
        # Declared here as well as in 0020 -- see the note on Article.
        Index(
            "ix_stories_centroid_hnsw",
            "centroid",
            postgresql_using="hnsw",
            postgresql_ops={"centroid": "halfvec_cosine_ops"},
        ),
    )


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
    # The slot a reader sees is picked from their browser's clock, so this is
    # not needed to render. It is here so a user who has told us once does not
    # have to tell us again on a second device.
    timezone: Mapped[str | None] = mapped_column(String(64))
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


class Team(Base):
    """Who a story is about. Reference data, seeded by the migration.

    Holds three kinds in one table -- 'team', 'conference' and 'league' -- so
    a story about the CBA or an expansion vote still gets tagged rather than
    falling through to nothing. Team codes are three characters and the other
    two kinds are longer, so a code's length distinguishes them without
    reading `kind`.

    Adding a team is an INSERT, not a migration, because code is the primary
    key -- which is also how a second league gets added later.
    """

    __tablename__ = "teams"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(12))
    sort_order: Mapped[int] = mapped_column(SmallInteger)

    # Null on the three scope rows: LEAGUE/EAST/WEST are not IN a conference,
    # they are one. Only kind='team' rows carry alignment.
    conference: Mapped[str | None] = mapped_column(String(4))
    division: Mapped[str | None] = mapped_column(String(16))
    # The scores provider's surrogate id, matched on abbreviation by the first
    # sync rather than seeded. Hardcoding another system's ids into a migration
    # makes their re-seed our migration.
    bdl_team_id: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("bdl_team_id", name="uq_teams_bdl_team_id"),)


class StoryTeam(Base):
    """Which teams a story concerns. Same shape as StoryCategory.

    Separate from story_categories rather than one polymorphic tag table:
    the two are validated differently -- categories against a list the model
    is shown, teams against one it is not -- and a team tab should never have
    to filter out category rows.
    """

    __tablename__ = "story_teams"

    story_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    team_code: Mapped[str] = mapped_column(
        String(8), ForeignKey("teams.code"), primary_key=True
    )
    # 0 is the primary team -- whose story it mostly is. In a trade, the side
    # the reporting leads with.
    rank: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Derived as 1/(rank+1) from the ordering the classifier already returns,
    # rather than asked of the model as a number. Models score their own
    # confidence badly, and rank is information already being given for free.
    relevance: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0", default=0.0
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    # Mirrors ix_story_categories_slug: the PK leads with story_id, so
    # "every story about the Lakers" needs the columns the other way round.
    __table_args__ = (Index("ix_story_teams_code", "team_code", "story_id"),)


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


class Game(Base):
    """One scheduled game, and every number a brief is allowed to quote.

    The strict division: RSS supplies narrative, this supplies statistics. A
    brief that says a player scored 38 read it from here. That is not a
    stylistic preference -- it is the only defence against a stale or
    hallucinated stat arriving through a headline, and it works by leaving
    nowhere else for a number to come from.
    """

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    # The provider's id, stable across re-polls of the same game -- which is
    # the entire reason we re-poll.
    bdl_game_id: Mapped[int] = mapped_column(Integer, unique=True)

    # TIP-OFF date in Eastern, computed by the poller rather than taken from
    # the provider's own date field. A 10:30pm ET tip ending at 1:15am is
    # still tonight's game, and "tonight's slate" is what every night-brief
    # query asks.
    game_date_et: Mapped[date] = mapped_column(Date)
    tipoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    home_team_code: Mapped[str] = mapped_column(String(8), ForeignKey("teams.code"))
    away_team_code: Mapped[str] = mapped_column(String(8), ForeignKey("teams.code"))

    # Normalized to scheduled | live | final by the poller, so the due check
    # never parses a display string. The provider sends a human-readable one
    # that walks "7:00 pm ET" -> "1st Qtr" -> ... -> "Final".
    status: Mapped[str] = mapped_column(String(16))
    # Beside status rather than folded into it, because the provider reports
    # them separately and the night trigger must tell "not finished yet" from
    # "will never finish" -- a postponement counted as pending would hang the
    # brief exactly like a stuck live game.
    postponed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)

    # OURS, not the provider's -- they publish no completion timestamp. Set
    # once, on the first poll that observes a final, and never rewritten. The
    # night brief's 30-minute wait measures from this, because it is the only
    # clock that exists.
    final_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    polled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_games_date_et", "game_date_et"),)


class BoxLine(Base):
    """One player's line in one game."""

    __tablename__ = "box_lines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    game_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("games.id", ondelete="CASCADE")
    )
    bdl_player_id: Mapped[int] = mapped_column(Integer)
    player_name: Mapped[str] = mapped_column(String(100))
    team_code: Mapped[str] = mapped_column(String(8), ForeignKey("teams.code"))

    # As the provider sends it -- "34:12" or "34". Parsing to an integer would
    # throw away the seconds for nothing: a brief quotes minutes, it does not
    # do arithmetic on them. Named `minutes` in Python because `min` shadows a
    # builtin; the column keeps the conventional box-score name.
    minutes: Mapped[str | None] = mapped_column("min", String(8))
    pts: Mapped[int | None] = mapped_column(SmallInteger)
    reb: Mapped[int | None] = mapped_column(SmallInteger)
    ast: Mapped[int | None] = mapped_column(SmallInteger)
    stl: Mapped[int | None] = mapped_column(SmallInteger)
    blk: Mapped[int | None] = mapped_column(SmallInteger)
    # The provider calls this `turnover`; mapped on read.
    tov: Mapped[int | None] = mapped_column(SmallInteger)
    plus_minus: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        UniqueConstraint("game_id", "bdl_player_id", name="uq_box_lines_game_player"),
        Index("ix_box_lines_game", "game_id"),
    )


class ScoreRun(Base):
    """One scores-poll attempt, successful or not.

    Mirrors FetchRun for the same reason it exists: a poller that stops is
    invisible until someone notices the data is stale -- and here the night
    brief's trigger depends on this data being current, so silence is worse
    than a visible error.
    """

    __tablename__ = "score_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    status: Mapped[str] = mapped_column(String(20))  # ok | error
    games_seen: Mapped[int | None] = mapped_column(Integer)
    box_lines_written: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_score_runs_started", "started_at"),)


class BriefSection(Base):
    """One pre-written piece of a brief. The cost model made physical.

    Generated per TEAM, never per user: one league section plus one per team
    with qualifying news, so a slot costs at most 31 generations however many
    people read it. A reader's brief is assembled from these rows at read
    time -- ten thousand Lakers fans consume one generation, and following
    twelve teams consumes none.

    team_code is NOT NULL, with league sections using the 'LEAGUE' code 0013
    already seeded. The obvious design -- nullable, NULL meaning league --
    silently breaks the guarantee this table exists to give, because Postgres
    treats NULL as distinct from NULL in a UNIQUE constraint. It would permit
    unlimited duplicate league sections while appearing to forbid them, and
    the league row is the one written every single slot.
    """

    __tablename__ = "brief_sections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    # The ET calendar date the slot belongs to, not the UTC date it was
    # written on: a night brief generated at 01:40 belongs to the day whose
    # games it recaps.
    slot_date: Mapped[date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(8))  # morning | midday | night
    scope: Mapped[str] = mapped_column(String(8))  # league | team
    team_code: Mapped[str] = mapped_column(String(8), ForeignKey("teams.code"))

    body_md: Mapped[str] = mapped_column(Text)
    # Counted server-side from body_md, never the model's self-report --
    # trusting it to count its own words makes the budget advisory.
    word_count: Mapped[int] = mapped_column(Integer)
    # Denormalized at write time so ordering a reader's team sections is one
    # indexed query with no join back to stories. Same trade as
    # summarized_outlet_count.
    max_importance: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0", default=0.0
    )

    # Which stories this section used. Not provenance decoration: the morning
    # brief reads the previous night's ids so it finishes that story rather
    # than retelling it.
    cluster_ids: Mapped[list[str]] = mapped_column(JSONB)
    game_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    # True when the p97 override lifted this section's budget. The assembly
    # cap reads it, because a major story is allowed to exceed the cap.
    is_major: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    model: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    __table_args__ = (
        # Load-bearing beyond deduplication: "no row for this slot" is how the
        # scheduler knows a slot has not run and how the reader knows to fall
        # back to an older one.
        UniqueConstraint(
            "slot_date", "slot", "team_code", name="uq_brief_sections_slot_team"
        ),
        Index("ix_brief_sections_slot", "slot_date", "slot"),
    )


class UserTeam(Base):
    """A team someone follows. Same shape as Favorite, for the same reasons."""

    __tablename__ = "user_teams"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    # No FK -- auth.users is Supabase's own schema and does not exist here.
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False))
    team_code: Mapped[str] = mapped_column(String(8), ForeignKey("teams.code"))
    followed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    __table_args__ = (
        # No cap on rows per user: following twelve teams costs nothing to
        # generate, and it is the assembly cap -- not the follow list -- that
        # keeps a brief readable.
        UniqueConstraint("user_id", "team_code", name="uq_user_teams_user_team"),
        Index("ix_user_teams_user", "user_id"),
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
