"""Shared schema. Both the worker and the app import from here.

Migrations are owned by Alembic and by the worker side only. The app never
alters schema.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
    __table_args__ = (
        Index("ix_fetch_runs_outlet_started", "outlet_id", "started_at"),
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
