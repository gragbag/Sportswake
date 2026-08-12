"""Resolve comments that could not be classified when they were posted.

    python -m worker.moderate        (make moderate)

`pending` means "we never got an answer" -- the provider was down, the quota
was gone, the reply was malformed. Without this pass those comments would
never appear and never be removed, which is exactly the silent-trash-can
failure that makes moderation read as a bug.

Runs alongside the other workers on the hourly cron. Comments that fail
again simply stay pending and are retried next hour, so a provider outage
delays publication rather than losing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.moderation import classify
from common.models import make_engine, make_session_factory

# Small: a provider that is down will fail all of them, and there is no
# point burning a whole rate-limit budget discovering that once an hour.
BATCH = 50


def resolve_pending(session, limit: int = BATCH) -> tuple[int, int, int]:
    """Re-classify pending comments. Returns (visible, removed, still_pending)."""
    rows = session.execute(
        text("""
            select id, body from comments
            where status = 'pending'
            order by created_at
            limit :limit
        """),
        {"limit": limit},
    ).all()

    counts = {"visible": 0, "removed": 0, "pending": 0}
    for row in rows:
        verdict = classify(row.body)
        counts[verdict.status] += 1
        if verdict.status == "pending":
            # Leave the row alone rather than writing the same value back;
            # created_at ordering then keeps the oldest retried first.
            continue
        session.execute(
            text("update comments set status = :status where id = :cid"),
            {"status": verdict.status, "cid": row.id},
        )
        session.commit()

    return counts["visible"], counts["removed"], counts["pending"]


def main() -> int:
    engine = make_engine()
    Session = make_session_factory(engine)
    with Session() as session:
        waiting = session.scalar(
            text("select count(*) from comments where status = 'pending'")
        )
        print(f"{waiting} comments pending classification")
        if not waiting:
            return 0
        published, removed, still = resolve_pending(session)
        print(f"  published {published}, removed {removed}, still pending {still}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
