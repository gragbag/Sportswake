"""Eyeball the embeddings by hand.

    python scripts/neighbors.py               # a random article
    python scripts/neighbors.py michigan      # first headline matching a term

If the top matches are not obviously the same story, the problem is in
article_text() or the model -- find that out before layering clustering on top.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from common.models import Article, Outlet, make_engine, make_session_factory

K = 10


def main() -> int:
    term = " ".join(sys.argv[1:]).strip()
    engine = make_engine()
    Session = make_session_factory(engine)

    with Session() as session:
        q = (
            session.query(Article, Outlet)
            .join(Outlet, Outlet.id == Article.outlet_id)
            .filter(Article.embedding.is_not(None))
        )
        q = (
            q.filter(Article.headline.ilike(f"%{term}%"))
            if term
            else q.order_by(text("random()"))
        )

        found = q.first()
        if found is None:
            print("no embedded article matches that term")
            return 1
        seed, seed_outlet = found

        print(f"\nSEED  [{seed_outlet.name}]")
        print(f"      {seed.headline}\n")

        dist = Article.embedding.cosine_distance(seed.embedding).label("dist")
        rows = (
            session.query(Article.headline, Outlet.name, dist)
            .join(Outlet, Outlet.id == Article.outlet_id)
            .filter(Article.embedding.is_not(None), Article.id != seed.id)
            .order_by(dist)
            .limit(K)
            .all()
        )

        print(f"  {'sim':>5}  {'outlet':<20} headline")
        for headline, outlet_name, d in rows:
            print(f"  {1 - d:>5.3f}  {outlet_name[:20]:<20} {headline[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
