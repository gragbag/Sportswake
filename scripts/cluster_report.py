"""Scorecard for one clustering run. Same numbers every time, so runs compare.

python scripts/cluster_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from common.config import (
    ACCEPT_COSINE,
    CANDIDATE_WINDOW_HOURS,
    TIME_DECAY_SIGMA_HOURS,
)
from common.models import make_engine

PROBES = [
    ("gaza funeral", "%funeral%gaza%"),
    ("el-sayed primary", "%el-sayed%senate primary%"),
]


def main() -> int:
    with make_engine().connect() as c:
        print(
            f"accept {ACCEPT_COSINE}  window {CANDIDATE_WINDOW_HOURS}h  "
            f"sigma {TIME_DECAY_SIGMA_HOURS}h"
        )
        a = c.execute(text("select count(*) from articles")).scalar()
        s = c.execute(text("select count(*) from stories")).scalar()
        singles = c.execute(
            text(
                "select count(*) from (select story_id from story_members "
                "group by 1 having count(*)=1) x"
            )
        ).scalar()
        print(
            f"  articles {a}   stories {s}   singletons {singles} "
            f"({100 * singles // max(s, 1)}%)"
        )

        big = c.execute(
            text("""
            select count(*) n, count(distinct a.outlet_id) outlets
            from story_members sm join articles a on a.id = sm.article_id
            group by sm.story_id order by n desc limit 1""")
        ).one()
        print(f"  largest cluster: {big[0]} articles / {big[1]} outlets")

        for label, pattern in PROBES:
            rows = c.execute(
                text("""
                select sm.story_id, count(*) from articles a
                join story_members sm on sm.article_id = a.id
                where lower(a.headline) like :p
                group by sm.story_id order by count(*) desc"""),
                {"p": pattern},
            ).all()
            shape = " + ".join(str(r[1]) for r in rows) or "none"
            print(
                f"  {label:<18} {len(rows)} stor{'y' if len(rows) == 1 else 'ies'} ({shape})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
