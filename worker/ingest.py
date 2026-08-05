"""Fetch every configured feed once and store new articles.

Run locally:   python -m worker.ingest
Run in CI:     see .github/workflows/ingest.yml

Idempotent by construction: articles are inserted with ON CONFLICT DO NOTHING
against (outlet_id, guid), so running this twice in a row is harmless.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import (
    Article,
    FetchRun,
    Outlet,
    make_engine,
    make_session_factory,
    utcnow,
)

FEEDS_FILE = Path(__file__).parent / "feeds.yaml"
USER_AGENT = "Presswake/0.1 (+https://github.com/gragbag/Presswake; firedragon1726@gmail.com)"
TIMEOUT = 20


def sync_outlets(session) -> list[Outlet]:
    """Seed outlets from feeds.yaml. Safe to run every time."""
    config = yaml.safe_load(FEEDS_FILE.read_text())
    for entry in config["feeds"]:
        stmt = (
            pg_insert(Outlet.__table__)
            .values(id=str(__import__("uuid").uuid4()),
                    name=entry["name"], feed_url=entry["url"])
            .on_conflict_do_nothing(index_elements=["feed_url"])
        )
        session.execute(stmt)
    session.commit()
    return session.query(Outlet).order_by(Outlet.name).all()


def parse_published(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def fetch_outlet(session, outlet: Outlet) -> None:
    run = FetchRun(outlet_id=outlet.id, status="error", started_at=utcnow())
    session.add(run)
    session.commit()

    headers = {"User-Agent": USER_AGENT}
    if outlet.etag:
        headers["If-None-Match"] = outlet.etag
    if outlet.last_modified:
        headers["If-Modified-Since"] = outlet.last_modified

    try:
        response = requests.get(outlet.feed_url, headers=headers, timeout=TIMEOUT)
        run.http_status = response.status_code

        if response.status_code == 304:
            run.status = "not_modified"
            run.finished_at = utcnow()
            session.commit()
            print(f"  {outlet.name}: unchanged")
            return

        

        response.raise_for_status()
        feed = feedparser.parse(response.content)

        run.payload_bytes = len(response.content)
        run.payload_hash = hashlib.sha256(response.content).hexdigest()

        inserted = 0
        for entry in feed.entries:
            guid = getattr(entry, "id", None) or getattr(entry, "link", None)
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not (guid and link and title):
                continue

            stmt = (
                pg_insert(Article.__table__)
                .values(
                    id=str(__import__("uuid").uuid4()),
                    outlet_id=outlet.id,
                    guid=guid,
                    url=link,
                    headline=title.strip(),
                    lede=(getattr(entry, "summary", "") or "")[:2000] or None,
                    published_at=parse_published(entry),
                )
                .on_conflict_do_nothing(constraint="uq_articles_outlet_guid")
            )
            inserted += session.execute(stmt).rowcount or 0

        outlet.etag = response.headers.get("ETag")
        outlet.last_modified = response.headers.get("Last-Modified")

        run.status = "ok"
        run.items_seen = len(feed.entries)
        run.items_inserted = inserted
        run.finished_at = utcnow()
        session.commit()
        print(f"  {outlet.name}: {len(feed.entries)} seen, {inserted} new")

    except Exception as exc:  # noqa: BLE001 - a failed outlet must not stop the rest
        session.rollback()
        run = session.get(FetchRun, run.id)
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"[:1000]
        run.finished_at = utcnow()
        session.commit()
        print(f"  {outlet.name}: FAILED - {exc}")


def main() -> int:
    engine = make_engine()
    Session = make_session_factory(engine)

    with Session() as session:
        outlets = sync_outlets(session)
        print(f"Fetching {len(outlets)} feeds")
        for outlet in outlets:
            fetch_outlet(session, outlet)

        total = session.query(Article).count()
        print(f"Done. {total} articles in corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())