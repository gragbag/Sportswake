"""Poll the scores provider into `games` and `box_lines`.

Run locally:   python -m worker.scores
Run in CI:     see .github/workflows/briefs.yml

This is the only source of numbers in the system. RSS supplies narrative and
reporting; every score, every stat line, every record comes from here. The
separation is not stylistic -- it is enforced by leaving nowhere else for a
number to come from, which is what stops a stale or hallucinated stat being
laundered through a summary.

Idempotent: games upsert on the provider's own id, box lines on
(game_id, player). Running twice in a row changes nothing, which matters
because the brief workflow runs this every fifteen minutes.

No API key is a supported state, not an error. Everything downstream treats
missing game data as "no linked game", so briefs keep working and simply
carry no box scores.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import and_, case, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import (
    BALLDONTLIE_API_KEY,
    BALLDONTLIE_BASE_URL,
    BALLDONTLIE_PACE_SECONDS,
    BALLDONTLIE_TIMEOUT_SECONDS,
    SCORES_BOX_BATCH_LIMIT,
    SCORES_LOOKAHEAD_DAYS,
    SCORES_LOOKBACK_DAYS,
)
from common.models import (
    BoxLine,
    Game,
    ScoreRun,
    Team,
    make_engine,
    make_session_factory,
    utcnow,
)

# Generation is anchored to Eastern because the NBA calendar is. A tip-off at
# 22:30 Pacific belongs to the day it started in ET, not the UTC day it
# happens to land on.
ET = ZoneInfo("America/New_York")

# The provider's `status` is a display string, not an enum: it walks
# "7:00 pm ET" -> "1st Qtr" -> "Halftime" -> ... -> "Final". Anything
# containing one of these is a game in progress. Everything that is neither
# final nor in progress has not started.
_LIVE_MARKERS = ("qtr", "halftime", "ot", "end of", "quarter")


def get_key() -> str | None:
    """None means the feature is off, not that something is wrong."""
    return BALLDONTLIE_API_KEY or None


def _get(path: str, params: dict[str, Any], key: str) -> dict:
    response = requests.get(
        f"{BALLDONTLIE_BASE_URL}/{path.lstrip('/')}",
        params=params,
        headers={"Authorization": key},
        timeout=BALLDONTLIE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _paged(path: str, params: dict[str, Any], key: str) -> Iterator[dict]:
    """Yield every record across the provider's cursor pagination.

    Paced rather than hammered: the tier allows 60 requests a minute and a
    full slate is a handful of pages, so there is no reason to go near it.
    """
    cursor: Any = None
    while True:
        page = dict(params, per_page=100)
        if cursor is not None:
            page["cursor"] = cursor
        payload = _get(path, page, key)

        yield from payload.get("data", [])

        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not cursor:
            return
        time.sleep(BALLDONTLIE_PACE_SECONDS)


def normalize_status(raw: str | None) -> str:
    """Collapse the provider's display string to scheduled | live | final.

    Done once, here, so that no query downstream ever parses a human-readable
    status -- the night trigger asks "are all of today's games final?" and
    that question should not depend on how the provider words a tip-off time.
    """
    value = (raw or "").strip().lower()
    if value == "final":
        return "final"
    if any(marker in value for marker in _LIVE_MARKERS):
        return "live"
    return "scheduled"


def _tipoff(record: dict) -> datetime | None:
    """The provider's ISO timestamp, as an aware datetime."""
    raw = record.get("datetime") or record.get("date")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    # A bare date arrives naive; treat it as ET midnight rather than UTC, or
    # every evening game would land on the wrong ET day.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ET)
    return parsed


def sync_team_ids(session, key: str) -> int:
    """Fill teams.bdl_team_id by matching the provider's roster to ours.

    Matched on abbreviation, falling back to full name. Deliberately NOT
    reusing categorize.py's alias table: that one repairs codes an LLM
    invented, a genuinely fuzzy problem. This maps one provider's fixed
    vocabulary, where a miss means their roster changed and a person should
    hear about it rather than have it silently papered over.
    """
    by_code: dict[str, Team] = {}
    by_name: dict[str, Team] = {}
    for team in session.query(Team).filter(Team.kind == "team").all():
        by_code[team.code.upper()] = team
        by_name[team.name.strip().lower()] = team

    matched, unmatched = 0, []
    for record in _paged("teams", {}, key):
        abbr = (record.get("abbreviation") or "").strip().upper()
        full = (record.get("full_name") or "").strip().lower()
        team = by_code.get(abbr) or by_name.get(full)
        if team is None:
            # Historical and All-Star franchises live in this endpoint too;
            # only report ones that look current.
            if record.get("conference"):
                unmatched.append(f"{abbr or '?'} / {record.get('full_name')}")
            continue
        if team.bdl_team_id != record["id"]:
            team.bdl_team_id = record["id"]
            matched += 1

    session.commit()
    if unmatched:
        print(f"  unmatched provider teams: {', '.join(unmatched)}")
    return matched


def _code_map(session) -> dict[int, str]:
    rows = session.query(Team.bdl_team_id, Team.code).filter(
        Team.bdl_team_id.isnot(None)
    )
    return {bdl_id: code for bdl_id, code in rows}


def _lookup(mapping: dict[int, str], node: Any) -> str | None:
    """Resolve a nested provider id against one of our maps.

    Every id in a provider payload is nested one level down and may simply be
    absent. Checking the type here rather than at four call sites keeps the
    callers readable and means a malformed record is skipped rather than
    raising midway through a run.
    """
    key = (node or {}).get("id")
    return mapping.get(key) if isinstance(key, int) else None


def sync_games(session, key: str, start: date, end: date) -> int:
    """Upsert every game in the window.

    `final_at` is the one column that is never overwritten. The provider
    publishes no completion timestamp, so the moment we first SEE a final is
    the only clock available -- and the night brief waits thirty minutes from
    it. Rewriting it on each poll would push that deadline forever forward.
    """
    codes = _code_map(session)
    seen = 0

    for record in _paged(
        "games",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        key,
    ):
        home = _lookup(codes, record.get("home_team"))
        away = _lookup(codes, record.get("visitor_team"))
        tipoff = _tipoff(record)
        if not (home and away and tipoff):
            # An exhibition or All-Star game against a franchise we do not
            # carry. Skipping beats failing the FK and losing the whole run.
            continue

        status = normalize_status(record.get("status"))
        values = {
            "id": str(__import__("uuid").uuid4()),
            "bdl_game_id": record["id"],
            "game_date_et": tipoff.astimezone(ET).date(),
            "tipoff_at": tipoff,
            "home_team_code": home,
            "away_team_code": away,
            "status": status,
            "postponed": bool(record.get("postponed")),
            "home_score": record.get("home_team_score"),
            "away_score": record.get("visitor_team_score"),
            "final_at": utcnow() if status == "final" else None,
            "polled_at": utcnow(),
        }

        stmt = pg_insert(Game).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["bdl_game_id"],
            set_={
                "game_date_et": stmt.excluded.game_date_et,
                "tipoff_at": stmt.excluded.tipoff_at,
                "status": stmt.excluded.status,
                "postponed": stmt.excluded.postponed,
                "home_score": stmt.excluded.home_score,
                "away_score": stmt.excluded.away_score,
                "polled_at": stmt.excluded.polled_at,
                # Stamp only on the transition INTO final, never after.
                "final_at": case(
                    (
                        and_(Game.final_at.is_(None), stmt.excluded.status == "final"),
                        func.now(),
                    ),
                    else_=Game.final_at,
                ),
            },
        )
        session.execute(stmt)
        seen += 1

    session.commit()
    return seen


def pending_box_games(session, limit: int) -> list[tuple[str, int]]:
    """Final games with no box lines yet, newest first."""
    rows = session.execute(
        text("""
            select g.id, g.bdl_game_id
            from games g
            where g.status = 'final'
              and not g.postponed
              and not exists (select 1 from box_lines b where b.game_id = g.id)
            order by g.game_date_et desc
            limit :limit
        """),
        {"limit": limit},
    ).all()
    return [(r.id, r.bdl_game_id) for r in rows]


def sync_box_lines(session, key: str, limit: int = SCORES_BOX_BATCH_LIMIT) -> int:
    """Pull per-player lines for finished games that do not have them."""
    pending = pending_box_games(session, limit)
    if not pending:
        return 0

    codes = _code_map(session)
    by_bdl_id = {bdl_id: game_id for game_id, bdl_id in pending}
    written = 0

    time.sleep(BALLDONTLIE_PACE_SECONDS)
    for record in _paged(
        "stats", {"game_ids[]": [bdl_id for _, bdl_id in pending]}, key
    ):
        game_id = _lookup(by_bdl_id, record.get("game"))
        team_code = _lookup(codes, record.get("team"))
        player = record.get("player") or {}
        if not (game_id and team_code and player.get("id")):
            continue

        name = " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        ).strip()

        values = {
            "id": str(__import__("uuid").uuid4()),
            "game_id": game_id,
            "bdl_player_id": player["id"],
            "player_name": name[:100] or "Unknown",
            "team_code": team_code,
            "min": record.get("min"),
            "pts": record.get("pts"),
            "reb": record.get("reb"),
            "ast": record.get("ast"),
            "stl": record.get("stl"),
            "blk": record.get("blk"),
            # Their name for it, ours in the column.
            "tov": record.get("turnover"),
            "plus_minus": record.get("plus_minus"),
        }
        stmt = pg_insert(BoxLine).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_box_lines_game_player",
            set_={
                k: getattr(stmt.excluded, k)
                for k in (
                    "min",
                    "pts",
                    "reb",
                    "ast",
                    "stl",
                    "blk",
                    "tov",
                    "plus_minus",
                    "player_name",
                    "team_code",
                )
            },
        )
        session.execute(stmt)
        written += 1

    session.commit()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days-back", type=int, default=SCORES_LOOKBACK_DAYS)
    parser.add_argument("--days-ahead", type=int, default=SCORES_LOOKAHEAD_DAYS)
    parser.add_argument("--limit", type=int, default=SCORES_BOX_BATCH_LIMIT)
    parser.add_argument(
        "--skip-teams",
        action="store_true",
        help="Skip the team-id sync; it only changes when their roster does.",
    )
    args = parser.parse_args()

    key = get_key()
    if key is None:
        print("BALLDONTLIE_API_KEY not set; skipping scores")
        return 0

    engine = make_engine()
    Session = make_session_factory(engine)

    with Session() as session:
        run = ScoreRun(status="error", started_at=utcnow())
        session.add(run)
        session.commit()

        try:
            if not args.skip_teams:
                linked = sync_team_ids(session, key)
                if linked:
                    print(f"Linked {linked} team ids")

            today = datetime.now(ET).date()
            start = today - timedelta(days=args.days_back)
            end = today + timedelta(days=args.days_ahead)
            seen = sync_games(session, key, start, end)
            print(f"{seen} games in {start} .. {end}")

            written = sync_box_lines(session, key, args.limit)
            print(f"{written} box lines written")

            run.status = "ok"
            run.games_seen = seen
            run.box_lines_written = written
            run.finished_at = utcnow()
            session.commit()

        except Exception as exc:  # noqa: BLE001 - the run row is the point
            session.rollback()
            run = session.get(ScoreRun, run.id)
            run.status = "error"
            run.error = f"{type(exc).__name__}: {exc}"[:1000]
            run.finished_at = utcnow()
            session.commit()
            print(f"FAILED - {exc}")
            return 1

    return 0


if __name__ == "__main__":
    # Player and team names carry accents, and a Windows console defaults to
    # cp1252 -- which raises rather than substitutes. See worker/importance.py.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    raise SystemExit(main())
