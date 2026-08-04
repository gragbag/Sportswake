"""Shared schema. Both the worker and the app import from here.

Migrations are owned by Alembic and by the worker side only. The app never
alters schema.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

def _uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Outlet(Base):
    __tablename__ = "outlets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    feed_url = Column(Text, nullable=False, unique=True)

    # Conditional-request state. Sending these back means unchanged feeds
    # return a cheap 304 instead of the full body.
    etag = Column(Text)
    last_modified = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class Article(Base):
    __tablename__ = "articles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    outlet_id = Column(UUID(as_uuid=False), ForeignKey("outlets.id"), nullable=False)

    # The outlet's own stable identifier for the item. More reliable than the
    # URL, which picks up tracking parameters and sometimes changes.
    guid = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    headline = Column(Text, nullable=False)
    lede = Column(Text)
    published_at = Column(DateTime(timezone=True))

    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Dedup key. Reruns and overlapping fetch windows are safe because inserts
    # use ON CONFLICT DO NOTHING against this constraint.
    __table_args__ = (UniqueConstraint("outlet_id", "guid", name="uq_articles_outlet_guid"),)


class FetchRun(Base):
    """One row per attempted fetch, successful or not.

    This table is what the /status page reads. A run that fails still gets a
    row -- silence is the failure mode we are trying to make visible.
    """

    __tablename__ = "fetch_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    outlet_id = Column(UUID(as_uuid=False), ForeignKey("outlets.id"), nullable=False)

    status = Column(String(20), nullable=False)  # ok | not_modified | error
    http_status = Column(Integer)
    payload_hash = Column(String(64))
    payload_bytes = Column(Integer)
    items_seen = Column(Integer, default=0)
    items_inserted = Column(Integer, default=0)
    error = Column(Text)

    started_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = Column(DateTime(timezone=True))


def make_engine(url: str | None = None, serverless: bool = False):
    """Build an engine.

    serverless=True disables pooling on our side, which is what you want when
    the app runs as short-lived instances behind Supabase's transaction-mode
    pooler. The worker is a long-lived process and should pool normally.
    """
    url = url or os.environ["DATABASE_URL"]
    kwargs = {"pool_pre_ping": True}
    if serverless:
        from sqlalchemy.pool import NullPool

        kwargs = {"poolclass": NullPool}
    return create_engine(url, **kwargs)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)