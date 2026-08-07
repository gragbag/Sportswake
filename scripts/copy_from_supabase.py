"""Copy outlets and articles from Supabase down to the local database.

    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/presswake
    python scripts/copy_from_supabase.py "<supabase-session-pooler-url>"

Data flows DOWN only. Supabase holds the archive RSS can never rebuild; local
is disposable scratch. This script refuses to write anywhere but localhost so
it cannot be run backwards by accident.

stories and story_members are deliberately NOT copied -- they are derived data.
You regenerate them locally with worker.cluster.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from common.models import Article, Outlet, make_engine, make_session_factory

BATCH = 500


def as_list(vector):
    if vector is None:
        return None
    return vector.tolist() if hasattr(vector, "tolist") else list(vector)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/copy_from_supabase.py <source-database-url>")
        return 1
    source_url = sys.argv[1]

    target_url = os.environ["DATABASE_URL"]
    host = urlparse(target_url).hostname or ""
    if host not in ("localhost", "127.0.0.1"):
        print(f"refusing to write to {host!r} -- target must be localhost")
        return 1

    Src = make_session_factory(make_engine(source_url))
    Dst = make_session_factory(make_engine(target_url))

    with Src() as src, Dst() as dst:
        outlets = src.query(Outlet).all()
        for o in outlets:
            dst.execute(
                pg_insert(Outlet)
                .values(
                    id=o.id,
                    name=o.name,
                    feed_url=o.feed_url,
                    etag=o.etag,
                    last_modified=o.last_modified,
                    created_at=o.created_at,
                )
                .on_conflict_do_nothing(index_elements=["feed_url"])
            )
        dst.commit()
        print(f"outlets: {len(outlets)}")

        total = src.query(Article).count()
        copied, offset = 0, 0
        while True:
            rows = (
                src.query(Article)
                .order_by(Article.first_seen_at)
                .offset(offset)
                .limit(BATCH)
                .all()
            )
            if not rows:
                break
            dst.execute(
                pg_insert(Article)
                .values(
                    [
                        {
                            "id": a.id,
                            "outlet_id": a.outlet_id,
                            "guid": a.guid,
                            "url": a.url,
                            "headline": a.headline,
                            "lede": a.lede,
                            "published_at": a.published_at,
                            "first_seen_at": a.first_seen_at,
                            "embedding": as_list(a.embedding),
                        }
                        for a in rows
                    ]
                )
                .on_conflict_do_nothing(constraint="uq_articles_outlet_guid")
            )
            dst.commit()
            copied += len(rows)
            offset += BATCH
            print(f"  articles {copied}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
