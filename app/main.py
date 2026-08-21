"""Milestone 1 app: proves the corpus exists and is growing.

Deliberately plain. Real design work happens at milestone 4, when there are
story pages worth designing. This page has one job: show that the worker ran
and the number went up.
"""

from __future__ import annotations

import html
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import current_user, optional_user
from app.handles import derive_handle
from app.moderation import classify
from common.config import (
    BRIEF_MAX_RENDERED_SECTIONS,
    BRIEF_TZ,
    COMMENT_MAX_DEPTH,
    COMMENT_MAX_LENGTH,
    COMMENT_MAX_PER_DAY,
    COMMENT_MAX_PER_HOUR,
    COMMENT_MAX_PER_STORY,
    COMMENT_PAGE_SIZE,
    USERNAME_COOLDOWN_DAYS,
    USERNAME_RESERVED,
)
from common.models import (
    Article,
    FetchRun,
    Outlet,
    Story,
    make_engine,
    make_session_factory,
    utcnow,
)

# serverless=True -> no client-side pooling. Use the transaction-mode pooler
# string (port 6543) here.
engine = make_engine(serverless=True)
Session = make_session_factory(engine)

app = FastAPI(title="Sportswake")

STYLE = """
:root { color-scheme: light dark; }
body { font: 15px/1.6 ui-sans-serif, system-ui, sans-serif;
       max-width: 46rem; margin: 3rem auto; padding: 0 1.25rem; }
h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: .25rem; }
p.sub { color: #6b7280; margin-top: 0; }
table { border-collapse: collapse; width: 100%; margin: 1.5rem 0; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #e5e7eb; }
th { font-weight: 500; color: #6b7280; font-size: .85rem; }
.err { color: #b91c1c; }
ol { padding-left: 1.2rem; }
li { margin-bottom: .5rem; }
li span { color: #6b7280; font-size: .85rem; }
a { color: inherit; }
"""


# The milestone-1 article list that used to live at "/" is gone: the React
# brief is mounted there now. /status stays -- it is an operational surface,
# not product, and a schedule that quietly stopped has to be visible
# somewhere.


@app.get("/status", response_class=HTMLResponse)
def status() -> str:
    """Ingestion health. A schedule that quietly stopped shows up here."""
    with Session() as session:
        outlets = session.query(Outlet).order_by(Outlet.name).all()
        rows = []
        for outlet in outlets:
            last = (
                session.query(FetchRun)
                .filter(FetchRun.outlet_id == outlet.id)
                .order_by(FetchRun.started_at.desc())
                .first()
            )
            count = (
                session.query(func.count(Article.id))
                .filter(Article.outlet_id == outlet.id)
                .scalar()
            )
            rows.append((outlet, last, count))

    body = "".join(
        f"<tr><td>{html.escape(o.name)}</td>"
        f'<td class="{"err" if last and last.status == "error" else ""}">'
        f"{html.escape(last.status) if last else 'never run'}</td>"
        f"<td>{last.started_at.strftime('%b %d, %H:%M UTC') if last else '&mdash;'}</td>"
        f"<td>{count:,}</td></tr>"
        for o, last, count in rows
    )

    return f"""<!doctype html><meta charset="utf-8">
<title>Crosscut &middot; status</title><style>{STYLE}</style>
<h1>Ingestion status</h1>
<p class="sub"><a href="/">back to corpus</a></p>
<table><tr><th>Outlet</th><th>Last run</th><th>When</th><th>Articles</th></tr>
{body}</table>"""


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/stats")
def api_stats() -> dict:
    """Corpus counters. Exists mostly to prove the React <-> API wiring."""
    with Session() as session:
        multi_outlet = session.execute(
            text(
                "select count(*) from ("
                "  select sm.story_id from story_members sm"
                "  join articles a on a.id = sm.article_id"
                "  group by sm.story_id having count(distinct a.outlet_id) > 1"
                ") x"
            )
        ).scalar()
        return {
            "articles": session.scalar(select(func.count()).select_from(Article)),
            "outlets": session.scalar(select(func.count()).select_from(Outlet)),
            "stories": session.scalar(select(func.count()).select_from(Story)),
            "multi_outlet_stories": multi_outlet,
        }


@app.get("/api/categories")
def api_categories(team: str | None = None) -> list[dict]:
    """The section index, with a count of stories in each.

    Counts come from the same visibility rule as the feed (2+ outlets), so a
    section never advertises stories it will not show. They will not sum to
    the story total -- a story can hold two categories.

    `team` narrows the counts the same way the feed narrows its rows. Without
    it the index sat above a team-filtered feed still quoting league-wide
    totals: /stories/t/LAL offered "Free Agency 58" and delivered five. The
    index and the feed have to be filtered by the same thing or the numbers
    are a promise the next click breaks.

    The count is over `eligible.story_id`, not `sc.story_id`. The left join
    does not discard anything, so counting the story_categories side counted
    ineligible stories too -- harmless while every categorised story happened
    to have two outlets, and silently wrong the moment one does not.
    """
    with Session() as session:
        params: dict = {}
        team_sql = ""
        if team:
            team_sql = """
                and exists (
                    select 1 from story_teams st
                    where st.story_id = sm.story_id and st.team_code = :team
                )
            """
            # Codes are stored uppercase; tolerate a hand-typed /t/lal.
            params["team"] = team.upper()
        rows = session.execute(
            text(f"""
                select c.slug, c.label, count(distinct eligible.story_id) as n
                from categories c
                left join story_categories sc on sc.category_slug = c.slug
                left join (
                    select sm.story_id
                    from story_members sm
                    join articles a on a.id = sm.article_id
                    where true {team_sql}
                    group by sm.story_id
                    having count(distinct a.outlet_id) >= 2
                ) eligible on eligible.story_id = sc.story_id
                group by c.slug, c.label, c.sort_order
                order by c.sort_order
            """),
            params,
        ).all()
    return [{"slug": r.slug, "label": r.label, "count": r.n} for r in rows]


@app.get("/api/teams")
def api_teams() -> list[dict]:
    """The team selector, with a count of stories for each.

    No eligibility subquery like /api/categories carries: teams are assigned
    by the same classify call as categories, and that call is gated on the
    same 2+ outlet floor the feed uses -- so every tagged story is
    feed-visible by construction.

    Ordered by sort_order, which puts LEAGUE/EAST/WEST first and the 30
    clubs after; `kind` is what the frontend groups on.
    """
    with Session() as session:
        rows = session.execute(
            text("""
                select t.code, t.name, t.kind, count(st.story_id) as n
                from teams t
                left join story_teams st on st.team_code = t.code
                group by t.code
                order by t.sort_order
            """)
        ).all()
    return [
        {"code": r.code, "name": r.name, "kind": r.kind, "count": r.n} for r in rows
    ]


SPARK_BUCKETS = 10

# The select list every card needs. Shared so the feed and the favorites list
# cannot drift into returning different shapes for the same component.
_CARD_COLUMNS = """
    s.id, s.title, s.summary_title, s.summary_subhead,
    count(*) as article_count,
    count(distinct a.outlet_id) as outlet_count,
    min(a.effective_at) as first_at,
    max(a.effective_at) as last_at
"""


def _attach_members(session, rows) -> list[dict]:
    """Turn aggregate rows into card payloads.

    One extra query for every story at once rather than per row -- N+1 here
    would be 24 round trips to Supabase for one page load.
    """
    if not rows:
        return []

    members = session.execute(
        text("""
            select sm.story_id, o.name,
                   a.effective_at as pub_at
            from story_members sm
            join articles a on a.id = sm.article_id
            join outlets o on o.id = a.outlet_id
            where sm.story_id in :ids
            order by pub_at
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": [r.id for r in rows]},
    ).all()

    # One query for every story's categories, not one per card. Ordered by
    # rank so element 0 is the primary label.
    cats = session.execute(
        text("""
            select sc.story_id, sc.category_slug, c.label
            from story_categories sc
            join categories c on c.slug = sc.category_slug
            where sc.story_id in :ids
            order by sc.rank
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": [r.id for r in rows]},
    ).all()
    cats_by_story: dict[str, list[dict]] = {}
    for story_id, slug, label in cats:
        cats_by_story.setdefault(str(story_id), []).append(
            {"slug": slug, "label": label}
        )

    # Same again for teams: rank 0 is the primary team -- whose story it
    # mostly is, the side the reporting leads with in a trade.
    team_rows = session.execute(
        text("""
            select st.story_id, st.team_code, t.name
            from story_teams st
            join teams t on t.code = st.team_code
            where st.story_id in :ids
            order by st.rank
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": [r.id for r in rows]},
    ).all()
    teams_by_story: dict[str, list[dict]] = {}
    for story_id, code, name in team_rows:
        teams_by_story.setdefault(str(story_id), []).append(
            {"code": code, "name": name}
        )

    by_story: dict[str, list] = {}
    for story_id, outlet, when in members:
        by_story.setdefault(str(story_id), []).append((outlet, when))

    out = []
    for row in rows:
        entries = by_story.get(str(row.id), [])
        span = (row.last_at - row.first_at).total_seconds()

        # Outlets in order of first publication -- who broke it reads first.
        seen: list[str] = []
        for outlet, _ in entries:
            if outlet not in seen:
                seen.append(outlet)

        buckets = [0] * SPARK_BUCKETS
        for _, when in entries:
            fraction = (when - row.first_at).total_seconds() / span if span else 0.0
            buckets[min(SPARK_BUCKETS - 1, int(fraction * SPARK_BUCKETS))] += 1

        out.append(
            {
                "id": str(row.id),
                "title": row.title,
                "summary_title": row.summary_title,
                "summary_subhead": row.summary_subhead,
                "article_count": row.article_count,
                "outlet_count": row.outlet_count,
                "first_at": row.first_at.isoformat(),
                "last_at": row.last_at.isoformat(),
                "span_hours": round(span / 3600, 1),
                "outlets": seen,
                "buckets": buckets,
                "categories": cats_by_story.get(str(row.id), []),
                "teams": teams_by_story.get(str(row.id), []),
            }
        )
    return out


@app.get("/api/stories")
def api_stories(
    limit: int = 24,
    offset: int = 0,
    category: str | None = None,
    team: str | None = None,
) -> list[dict]:
    """Stories worth rendering, most-covered first.

    Singletons are excluded here, not from the corpus -- they are what supports
    "only one outlet covered this", so they stay in the database and stay out
    of the feed.

    `category` and `team` each filter via their own tag table, and they
    compose: /t/LAL + /c/trades is "Lakers trade stories". Both are bound
    parameters, never interpolated -- the f-string only ever assembles
    fixed SQL fragments.
    """
    with Session() as session:
        filter_sql = ""
        # Offset pagination is fine here: the feed is small (hundreds of
        # eligible stories) and the ordering is stable enough between "More"
        # clicks that a shifted row is rare and harmless.
        params: dict = {"limit": limit, "offset": max(0, offset)}
        if category:
            filter_sql += """
                and exists (
                    select 1 from story_categories sc
                    where sc.story_id = s.id and sc.category_slug = :category
                )
            """
            params["category"] = category
        if team:
            filter_sql += """
                and exists (
                    select 1 from story_teams st
                    where st.story_id = s.id and st.team_code = :team
                )
            """
            # Codes are stored uppercase; tolerate a hand-typed /t/lal.
            params["team"] = team.upper()
        rows = session.execute(
            text(f"""
                select {_CARD_COLUMNS}
                from stories s
                join story_members sm on sm.story_id = s.id
                join articles a on a.id = sm.article_id
                where true {filter_sql}
                group by s.id
                having count(distinct a.outlet_id) >= 2
                order by count(distinct a.outlet_id) desc, max(
                    a.effective_at) desc
                limit :limit offset :offset
            """),
            params,
        ).all()
        return _attach_members(session, rows)


@app.get("/api/me")
def api_me(user: Annotated[dict, Depends(current_user)]) -> dict:
    """Who the caller is, per their token. 401 when signed out.

    Exists to prove the auth round-trip end to end before anything depends
    on it. `sub` is the Supabase user id that favorites and notes will key
    against in the rest of milestone 6.
    """
    return {
        "id": user["sub"],
        "email": user.get("email"),
        "role": user.get("role"),
    }


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


class UsernameIn(BaseModel):
    username: str


def _validate_username(raw: str) -> str:
    """Return the cleaned username or raise 422. Format rules only."""
    name = raw.strip()
    if not _USERNAME_RE.match(name):
        raise HTTPException(
            422, "3-20 characters, letters, numbers and underscore only"
        )
    if name.lower() in USERNAME_RESERVED:
        raise HTTPException(422, "that name is reserved")
    return name


@app.get("/api/profile")
def api_profile(user: Annotated[dict, Depends(current_user)]) -> dict:
    """The signed-in user's own profile.

    `handle` is what actually renders: the chosen username when there is
    one, the derived handle otherwise. `username` stays null so the settings
    form can tell "I picked this" from "this was assigned to me".
    """
    with Session() as session:
        row = session.execute(
            text("""
                select username, username_changed_at, hide_comment_history
                from profiles where user_id = :uid
            """),
            {"uid": user["sub"]},
        ).one_or_none()

    username = row.username if row else None
    changed_at = row.username_changed_at if row else None

    # Surfaced so the UI can disable the form and say when, rather than
    # letting someone type a name and only then be told no.
    next_change = None
    if changed_at:
        next_change = changed_at + timedelta(days=USERNAME_COOLDOWN_DAYS)

    return {
        "user_id": user["sub"],
        "email": user.get("email"),
        "username": username,
        "handle": username or derive_handle(user["sub"]),
        "can_change_at": next_change.isoformat() if next_change else None,
        "hide_comment_history": bool(row.hide_comment_history) if row else False,
    }


@app.get("/api/username-available")
def api_username_available(username: str) -> dict:
    """Advisory check for the rename form.

    Public because it is only usable by someone already choosing a name, and
    a username is public by nature -- it appears on every comment. Email
    existence is the thing worth hiding, and this endpoint never touches it.
    """
    try:
        name = _validate_username(username)
    except HTTPException as exc:
        return {"available": False, "reason": exc.detail}

    with Session() as session:
        taken = session.execute(
            text("select 1 from profiles where lower(username) = lower(:n)"),
            {"n": name},
        ).first()

    return {"available": taken is None, "reason": None if taken is None else "taken"}


@app.patch("/api/profile")
def api_profile_update(
    payload: UsernameIn, user: Annotated[dict, Depends(current_user)]
) -> dict:
    """Choose or change a username."""
    name = _validate_username(payload.username)

    with Session() as session:
        existing = session.execute(
            text("""
                select username, username_changed_at
                from profiles where user_id = :uid
            """),
            {"uid": user["sub"]},
        ).one_or_none()

        # No-op rather than burning the cooldown on a form resubmit.
        if existing and existing.username == name:
            return {"username": name, "handle": name}

        if existing and existing.username_changed_at:
            ready = existing.username_changed_at + timedelta(
                days=USERNAME_COOLDOWN_DAYS
            )
            if utcnow() < ready:
                raise HTTPException(
                    429, f"you can change your username again after {ready:%b %d, %Y}"
                )

        # The unique index is the real arbiter -- the availability check
        # above it is advisory and can lose a race.
        try:
            session.execute(
                text("""
                    insert into profiles (user_id, username, username_changed_at)
                    values (:uid, :name, now())
                    on conflict (user_id) do update
                        set username = excluded.username,
                            username_changed_at = now()
                """),
                {"uid": user["sub"], "name": name},
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            raise HTTPException(409, "that username is taken") from None

    return {"username": name, "handle": name}


@app.patch("/api/profile/privacy")
def api_profile_privacy(
    payload: PrivacyIn, user: Annotated[dict, Depends(current_user)]
) -> dict:
    """Show or hide the aggregated comment history on the public profile.

    Hiding does not unpublish anything -- individual comments stay on their
    story pages, because deleting them is a different action with different
    consequences for the threads they are part of.
    """
    with Session() as session:
        session.execute(
            text("""
                insert into profiles (user_id, hide_comment_history)
                values (:uid, :hide)
                on conflict (user_id) do update
                    set hide_comment_history = excluded.hide_comment_history
            """),
            {"uid": user["sub"], "hide": payload.hide_comment_history},
        )
        session.commit()
    return {"hide_comment_history": payload.hide_comment_history}


@app.get("/api/users/{handle}")
def api_public_profile(
    handle: str, viewer: Annotated[dict | None, Depends(optional_user)]
) -> dict:
    """A public profile, addressed by chosen username or user id.

    Both work because most people never choose a name: their handle is
    derived from the uuid and cannot be reversed, so the id is the only
    thing that addresses them.
    """
    viewer_id = viewer["sub"] if viewer else None

    with Session() as session:
        row = session.execute(
            text("""
                select user_id, username, hide_comment_history, created_at
                from profiles where lower(username) = lower(:h)
            """),
            {"h": handle},
        ).one_or_none()

        user_id = str(row.user_id) if row else None
        if user_id is None:
            # Not a chosen username -- try it as a user id.
            try:
                uuid.UUID(handle)
            except ValueError:
                raise HTTPException(404, "no such user") from None
            user_id = handle
            row = session.execute(
                text("""
                    select user_id, username, hide_comment_history, created_at
                    from profiles where user_id = :uid
                """),
                {"uid": user_id},
            ).one_or_none()

        hidden = bool(row.hide_comment_history) if row else False
        # Your own history is always visible to you, or the toggle would
        # hide the thing you are trying to check.
        show = (not hidden) or viewer_id == user_id

        comments = []
        if show:
            rows = session.execute(
                text(f"""
                    select c.id, c.user_id, p.username, c.body,
                           c.created_at, c.edited_at,
                           coalesce(v.score, 0) as score,
                           coalesce(mine.value, 0) as my_vote,
                           c.story_id,
                           coalesce(s.summary_title, s.title) as story_title
                    from comments c
                    left join profiles p on p.user_id = c.user_id
                    join stories s on s.id = c.story_id
                    {_VOTE_JOIN}
                    where c.user_id = :uid
                      and c.visibility = 'public'
                      and c.status = 'visible'
                    order by c.created_at desc
                    limit :limit
                """),
                {
                    "uid": user_id,
                    "viewer": viewer_id,
                    "limit": COMMENT_PAGE_SIZE,
                },
            ).all()
            comments = [
                {
                    **_comment_payload(r),
                    "story_id": str(r.story_id),
                    "story_title": r.story_title,
                }
                for r in rows
            ]

    return {
        "user_id": user_id,
        "handle": (row.username if row and row.username else derive_handle(user_id)),
        "joined_at": row.created_at.isoformat() if row else None,
        "is_self": viewer_id == user_id,
        "history_hidden": hidden,
        "comments": comments,
    }


def _valid_uuid(value: str) -> str:
    """404 rather than 500 on a malformed id.

    story_id columns are uuid, so a junk string reaches Postgres as a failed
    cast and surfaces as a server error unless it is rejected here.
    """
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=404, detail="story not found") from None
    return value


@app.get("/api/favorites")
def api_favorites(user: Annotated[dict, Depends(current_user)]) -> list[dict]:
    """The signed-in user's saved stories, most recently saved first.

    Same card shape as /api/stories so the frontend renders both with one
    component.
    """
    with Session() as session:
        rows = session.execute(
            text(f"""
                select {_CARD_COLUMNS}, f.saved_at
                from favorites f
                join stories s on s.id = f.story_id
                join story_members sm on sm.story_id = s.id
                join articles a on a.id = sm.article_id
                where f.user_id = :uid
                group by s.id, f.saved_at
                order by f.saved_at desc
            """),
            {"uid": user["sub"]},
        ).all()
        return _attach_members(session, rows)


@app.get("/api/favorites/ids")
def api_favorite_ids(user: Annotated[dict, Depends(current_user)]) -> list[str]:
    """Just the ids, so the feed can render filled/empty stars in one request
    instead of asking per card."""
    with Session() as session:
        rows = session.execute(
            text("select story_id from favorites where user_id = :uid"),
            {"uid": user["sub"]},
        ).all()
    return [str(r.story_id) for r in rows]


@app.put("/api/favorites/{story_id}")
def api_favorite_add(
    story_id: str, user: Annotated[dict, Depends(current_user)]
) -> Response:
    """Save a story. PUT, not POST: favoriting twice is the same as once, and
    the unique constraint makes the insert genuinely idempotent."""
    _valid_uuid(story_id)
    with Session() as session:
        exists = session.execute(
            text("select 1 from stories where id = :sid"), {"sid": story_id}
        ).first()
        if exists is None:
            # Without this the FK raises IntegrityError and FastAPI returns a
            # 500 for what is really a bad request.
            raise HTTPException(status_code=404, detail="story not found")

        session.execute(
            text("""
                insert into favorites (id, user_id, story_id)
                values (gen_random_uuid(), :uid, :sid)
                on conflict (user_id, story_id) do nothing
            """),
            {"uid": user["sub"], "sid": story_id},
        )
        session.commit()
    # 204 declared here rather than on the decorator: FastAPI asserts that a
    # decorator status_code of 204 has no response field, and a `-> None`
    # annotation still creates one.
    return Response(status_code=204)


@app.delete("/api/favorites/{story_id}")
def api_favorite_remove(
    story_id: str, user: Annotated[dict, Depends(current_user)]
) -> Response:
    """Unsave. Deleting something already gone is a success, not a 404 --
    the end state the caller asked for is the end state they get."""
    _valid_uuid(story_id)
    with Session() as session:
        session.execute(
            text("delete from favorites where user_id = :uid and story_id = :sid"),
            {"uid": user["sub"], "sid": story_id},
        )
        session.commit()
    return Response(status_code=204)


class CommentIn(BaseModel):
    body: str
    parent_id: str | None = None


def _check_rate_limits(session, user_id: str, story_id: str) -> None:
    """Raise 429 if the user is over any limit. Runs BEFORE moderation.

    Order matters more than the limits themselves: this is one indexed query
    against a local table, whereas moderation is a network call. Check the
    free thing first and a spammer's cost stays at a database round trip
    instead of an API call per attempt.

    Counts rows over a trailing window rather than decrementing a stored
    counter -- the same reasoning the summary quota uses. Counters drift and
    cannot be audited after a bug; a count is always the truth.
    """
    counts = session.execute(
        text("""
            select
              count(*) filter (where created_at > now() - interval '1 hour') as hour,
              count(*) filter (where created_at > now() - interval '1 day')  as day,
              count(*) filter (where story_id = :sid)                        as story
            from comments
            where user_id = :uid and status <> 'removed'
        """),
        {"uid": user_id, "sid": story_id},
    ).one()

    # Removed comments still count toward the story cap above but not toward
    # rate windows, so deleting spam does not hand back budget to spam.
    if counts.hour >= COMMENT_MAX_PER_HOUR:
        raise HTTPException(429, f"limit is {COMMENT_MAX_PER_HOUR} comments per hour")
    if counts.day >= COMMENT_MAX_PER_DAY:
        raise HTTPException(429, f"limit is {COMMENT_MAX_PER_DAY} comments per day")
    if counts.story >= COMMENT_MAX_PER_STORY:
        raise HTTPException(429, f"limit is {COMMENT_MAX_PER_STORY} comments per story")


class VoteIn(BaseModel):
    value: int


class CommentEditIn(BaseModel):
    body: str


@app.patch("/api/comments/{comment_id}")
def api_comment_edit(
    comment_id: str,
    payload: CommentEditIn,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    """Edit your own comment.

    The edited text is re-classified. Skipping that would make editing a
    trivial moderation bypass: post something innocuous, wait for it to pass,
    then change it to whatever you actually wanted to say.

    A rejected edit is DISCARDED, not applied -- the comment keeps the text
    that was already approved and stays visible and editable. The earlier
    design applied the edit and let it be removed, which froze the comment,
    because a removed one cannot be edited again. That punished the case it
    was least meant for: quoting a threat in order to condemn it scores high
    on violence, and losing your comment for discussing what someone said is
    a bad trade against an attacker who can test wording directly against
    the classifier's own free public endpoint anyway.
    """
    _valid_uuid(comment_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, "comment is empty")
    if len(body) > COMMENT_MAX_LENGTH:
        raise HTTPException(422, f"comment exceeds {COMMENT_MAX_LENGTH} characters")

    with Session() as session:
        row = session.execute(
            text("select user_id, status from comments where id = :cid"),
            {"cid": comment_id},
        ).one_or_none()
        if row is None:
            raise HTTPException(404, "comment not found")
        if str(row.user_id) != user["sub"]:
            # 404 rather than 403: whether someone else's comment id exists
            # is not information this caller needs.
            raise HTTPException(404, "comment not found")
        if row.status in ("deleted", "removed"):
            raise HTTPException(409, "that comment is no longer editable")

        verdict = classify(body)

        if verdict.status == "removed":
            # Nothing is written. The caller is told plainly so they can
            # reword, rather than discovering their comment vanished.
            raise HTTPException(
                422,
                "That edit was not accepted by moderation, so your comment is "
                "unchanged. Try rewording it.",
            )
        if verdict.status == "pending":
            # Deliberately unlike the create path, which stores a pending
            # comment and lets the retry worker resolve it. Here there is an
            # already-approved version to protect, so an unverifiable edit
            # waits rather than replacing it.
            raise HTTPException(
                503, "Moderation is unavailable right now. Try again shortly."
            )

        session.execute(
            text("""
                update comments
                set body = :body, edited_at = now(), status = 'visible'
                where id = :cid
            """),
            {"body": body, "cid": comment_id},
        )
        session.commit()

    return {"id": comment_id, "body": body, "status": "visible"}


@app.delete("/api/comments/{comment_id}")
def api_comment_delete(
    comment_id: str, user: Annotated[dict, Depends(current_user)]
) -> dict:
    """Withdraw your own comment.

    A status change, never a row delete. If the comment has replies it stays
    as a tombstone so the answers beneath it still make sense; if it has
    none, the read query drops it entirely. Either way the text stops being
    served, and the row survives for moderation history.
    """
    _valid_uuid(comment_id)
    with Session() as session:
        row = session.execute(
            text("select user_id from comments where id = :cid"),
            {"cid": comment_id},
        ).one_or_none()
        if row is None or str(row.user_id) != user["sub"]:
            raise HTTPException(404, "comment not found")

        session.execute(
            text("update comments set status = 'deleted' where id = :cid"),
            {"cid": comment_id},
        )
        session.commit()

    return {"id": comment_id, "status": "deleted"}


class PrivacyIn(BaseModel):
    hide_comment_history: bool


# Score and the caller's own vote, joined onto any comment query. Kept as one
# string so the story thread and a user's history cannot drift into scoring
# comments differently.
_VOTE_JOIN = """
    left join (
        select comment_id,
               coalesce(sum(value), 0) as score,
               count(*) filter (where value = 1)  as ups,
               count(*) filter (where value = -1) as downs
        from comment_votes group by comment_id
    ) v on v.comment_id = c.id
    left join comment_votes mine
           on mine.comment_id = c.id and mine.user_id = :viewer
"""


@app.put("/api/comments/{comment_id}/vote")
def api_vote(
    comment_id: str, payload: VoteIn, user: Annotated[dict, Depends(current_user)]
) -> dict:
    """Cast or change a vote. Sending the vote you already hold clears it,
    which is how every arrow-based UI behaves."""
    _valid_uuid(comment_id)
    if payload.value not in (1, -1):
        raise HTTPException(422, "value must be 1 or -1")

    with Session() as session:
        if (
            session.execute(
                text("select 1 from comments where id = :cid and status = 'visible'"),
                {"cid": comment_id},
            ).first()
            is None
        ):
            raise HTTPException(404, "comment not found")

        current = session.execute(
            text("""
                select value from comment_votes
                where comment_id = :cid and user_id = :uid
            """),
            {"cid": comment_id, "uid": user["sub"]},
        ).scalar()

        if current == payload.value:
            session.execute(
                text("""
                    delete from comment_votes
                    where comment_id = :cid and user_id = :uid
                """),
                {"cid": comment_id, "uid": user["sub"]},
            )
            my_vote = 0
        else:
            # Upsert on the composite key: one vote per person per comment
            # is the primary key, so a change can never create a second row.
            session.execute(
                text("""
                    insert into comment_votes (comment_id, user_id, value)
                    values (:cid, :uid, :val)
                    on conflict (comment_id, user_id)
                        do update set value = excluded.value
                """),
                {"cid": comment_id, "uid": user["sub"], "val": payload.value},
            )
            my_vote = payload.value

        score = session.execute(
            text(
                "select coalesce(sum(value), 0) from comment_votes where comment_id = :cid"
            ),
            {"cid": comment_id},
        ).scalar()
        session.commit()

    return {"comment_id": comment_id, "score": score, "my_vote": my_vote}


@app.get("/api/stories/{story_id}/comments")
def api_comments(
    story_id: str,
    viewer: Annotated[dict | None, Depends(optional_user)],
    limit: int = COMMENT_PAGE_SIZE,
) -> list[dict]:
    """Public comments on a story, highest scoring first.

    Optional auth: signed out still reads the thread, signed in additionally
    learns which comments they have voted on so the arrows render filled.

    Only 'visible' rows are returned -- pending, hidden, and removed are all
    invisible to readers, and the distinction matters only to moderation.
    """
    _valid_uuid(story_id)
    viewer_id = viewer["sub"] if viewer else None

    with Session() as session:
        rows = session.execute(
            text(f"""
                select c.id, c.user_id, p.username, c.body,
                       c.created_at, c.edited_at, c.parent_id, c.depth,
                       c.status,
                       coalesce(v.score, 0) as score,
                       coalesce(mine.value, 0) as my_vote
                from comments c
                -- LEFT: most users never choose a name, so username comes
                -- back null and the derived handle takes over. Joining at
                -- read time is what makes a rename show up on every old
                -- comment at once instead of needing a rewrite.
                left join profiles p on p.user_id = c.user_id
                {_VOTE_JOIN}
                where c.story_id = :sid
                  and c.visibility = 'public'
                  and (
                    c.status = 'visible'
                    -- A withdrawn or removed comment stays ONLY while it has
                    -- replies, as a tombstone. Dropping it would orphan the
                    -- answers beneath it; keeping childless ones would
                    -- litter the thread with scars nobody can read.
                    or (c.status in ('deleted', 'removed')
                        and exists (select 1 from comments child
                                    where child.parent_id = c.id))
                  )
                -- created_at breaks ties so ordering is stable across
                -- reloads; without it equal-scoring comments shuffle.
                order by coalesce(v.score, 0) desc, c.created_at
                limit :limit
            """),
            {
                "sid": story_id,
                "viewer": viewer_id,
                "limit": min(limit, COMMENT_PAGE_SIZE),
            },
        ).all()

    return [_comment_payload(r) for r in rows]


def _comment_payload(r) -> dict:
    """One comment as the API returns it, wherever it is being listed."""
    status = getattr(r, "status", "visible")
    gone = status in ("deleted", "removed")
    return {
        "id": str(r.id),
        "parent_id": str(r.parent_id) if getattr(r, "parent_id", None) else None,
        "depth": getattr(r, "depth", 0),
        "status": status,
        # The author's uuid, not their email: an email address is personal
        # data and does not belong in a public payload. The frontend needs
        # it only to mark a comment as its own.
        "user_id": str(r.user_id),
        # Resolved server-side so every surface agrees on what to call
        # someone, rather than each component reimplementing the fallback.
        # A tombstone has no author and no text. The row keeps both for
        # moderation history; the API simply stops serving them.
        "author": None if gone else (r.username or derive_handle(str(r.user_id))),
        "body": None if gone else r.body,
        "created_at": r.created_at.isoformat(),
        "edited_at": r.edited_at.isoformat() if r.edited_at else None,
        "score": r.score,
        "my_vote": r.my_vote,
    }


@app.post("/api/stories/{story_id}/comments", status_code=201)
def api_comment_create(
    story_id: str,
    payload: CommentIn,
    user: Annotated[dict, Depends(current_user)],
) -> dict:
    """Post a comment. Checks run cheapest-first."""
    _valid_uuid(story_id)

    body = payload.body.strip()
    # 1. Free checks, no database round trip at all.
    if not body:
        raise HTTPException(422, "comment is empty")
    if len(body) > COMMENT_MAX_LENGTH:
        raise HTTPException(422, f"comment exceeds {COMMENT_MAX_LENGTH} characters")

    with Session() as session:
        if (
            session.execute(
                text("select 1 from stories where id = :sid"), {"sid": story_id}
            ).first()
            is None
        ):
            raise HTTPException(404, "story not found")

        # A reply inherits its parent's depth plus one. Reading the parent
        # also confirms it belongs to THIS story -- otherwise a crafted
        # parent_id could graft a reply onto a thread it was never part of.
        depth = 0
        parent_id = payload.parent_id
        if parent_id is not None:
            _valid_uuid(parent_id)
            parent = session.execute(
                text("""
                    select depth, story_id from comments
                    where id = :pid
                      and status in ('visible', 'deleted', 'removed')
                """),
                {"pid": parent_id},
            ).one_or_none()
            if parent is None or str(parent.story_id) != story_id:
                raise HTTPException(404, "parent comment not found")
            depth = parent.depth + 1
            if depth > COMMENT_MAX_DEPTH:
                raise HTTPException(422, "this thread is too deep to reply to")

        # 2. Indexed count, still free.
        _check_rate_limits(session, user["sub"], story_id)

        # 3. Duplicate guard: reposting identical text is the cheapest spam
        #    there is, and catching it here costs one more indexed lookup.
        if (
            session.execute(
                text("""
                select 1 from comments
                where user_id = :uid and story_id = :sid and body = :body
                  and status <> 'removed'
            """),
                {"uid": user["sub"], "sid": story_id, "body": body},
            ).first()
            is not None
        ):
            raise HTTPException(409, "you already posted that")

        # 4. The only paid check, and only reached by comments that already
        #    passed everything free. classify() never raises -- a failure
        #    returns 'pending', so the comment is stored either way and the
        #    retry worker resolves it.
        verdict = classify(body)

        row = session.execute(
            text("""
                insert into comments
                    (id, user_id, story_id, parent_id, depth, body, status)
                values
                    (gen_random_uuid(), :uid, :sid, :pid, :depth, :body, :status)
                returning id, created_at
            """),
            {
                "uid": user["sub"],
                "sid": story_id,
                "pid": parent_id,
                "depth": depth,
                "body": body,
                "status": verdict.status,
            },
        ).one()

        # Resolved the same way the read path does it, so a freshly posted
        # comment shows the same name as it will after a reload.
        chosen = session.execute(
            text("select username from profiles where user_id = :uid"),
            {"uid": user["sub"]},
        ).scalar()
        session.commit()

    return {
        "id": str(row.id),
        "parent_id": parent_id,
        "depth": depth,
        "status": verdict.status,
        "user_id": user["sub"],
        "author": chosen or derive_handle(user["sub"]),
        "body": body,
        "created_at": row.created_at.isoformat(),
        "edited_at": None,
        # A brand new comment has no votes yet, but the shape must match the
        # read path or the component renders it differently from its
        # neighbours.
        "score": 0,
        "my_vote": 0,
    }


@app.get("/api/stories/{story_id}")
def api_story(story_id: str) -> dict:
    """One story, with every member article.

    Unlike /api/stories this returns the full member list rather than one
    row per outlet: the sources section is a completeness claim, and the
    headline comparison is the product -- both want everything.
    """
    _valid_uuid(story_id)

    with Session() as session:
        # group by s.id alone is legal: it is the primary key, so Postgres
        # treats the other stories columns as functionally dependent.
        row = session.execute(
            text("""
                select s.id, s.title, s.summary_title, s.summary_subhead,
                       s.summary_bullets, s.summary_people, s.summary_model,
                       s.summarized_at,
                       count(*) as article_count,
                       count(distinct a.outlet_id) as outlet_count,
                       min(a.effective_at) as first_at,
                       max(a.effective_at) as last_at
                from stories s
                join story_members sm on sm.story_id = s.id
                join articles a on a.id = sm.article_id
                where s.id = :sid
                group by s.id
            """),
            {"sid": story_id},
        ).one_or_none()

        if row is None:
            raise HTTPException(status_code=404, detail="story not found")

        # NOT "as t": SQLAlchemy Row owns a legacy .t attribute that would
        # shadow a column of that name.
        articles = session.execute(
            text("""
                select o.name as outlet, a.headline, a.url,
                       a.effective_at as pub_at
                from story_members sm
                join articles a on a.id = sm.article_id
                join outlets o on o.id = a.outlet_id
                where sm.story_id = :sid
                order by pub_at
            """),
            {"sid": story_id},
        ).all()

        # Same shape and ordering as the feed's, so the card and the page can
        # share one badge component: rank 0 first, empty list when untagged.
        categories = session.execute(
            text("""
                select sc.category_slug as slug, c.label
                from story_categories sc
                join categories c on c.slug = sc.category_slug
                where sc.story_id = :sid
                order by sc.rank
            """),
            {"sid": story_id},
        ).all()

        teams = session.execute(
            text("""
                select st.team_code as code, t.name
                from story_teams st
                join teams t on t.code = st.team_code
                where st.story_id = :sid
                order by st.rank
            """),
            {"sid": story_id},
        ).all()

    span = (row.last_at - row.first_at).total_seconds()
    return {
        "id": str(row.id),
        "title": row.title,
        # JSONB decodes to real lists; null stays null for unsummarized.
        "summary_title": row.summary_title,
        "summary_subhead": row.summary_subhead,
        "summary_bullets": row.summary_bullets,
        "summary_people": row.summary_people,
        "summary_model": row.summary_model,
        "summarized_at": row.summarized_at.isoformat() if row.summarized_at else None,
        "article_count": row.article_count,
        "outlet_count": row.outlet_count,
        "first_at": row.first_at.isoformat(),
        "last_at": row.last_at.isoformat(),
        "span_hours": round(span / 3600, 1),
        "categories": [{"slug": c.slug, "label": c.label} for c in categories],
        "teams": [{"code": t.code, "name": t.name} for t in teams],
        "articles": [
            {
                "outlet": a.outlet,
                "headline": a.headline,
                "url": a.url,
                "published_at": a.pub_at.isoformat(),
            }
            for a in articles
        ],
    }


# ---- briefs ---------------------------------------------------------------


class TeamsIn(BaseModel):
    codes: list[str]


def _preferred_slot(local_hour: int) -> str:
    """Which brief a reader most likely wants, from THEIR clock.

    Generation is anchored to Eastern because the NBA calendar is; display is
    anchored to the reader. The two are deliberately separate -- a reader in
    Los Angeles opening the app at 21:00 wants the night brief, whatever the
    hour is in New York.
    """
    if 5 <= local_hour < 12:
        return "morning"
    if 12 <= local_hour < 18:
        return "midday"
    return "night"


def _resolve_slot(session, slot: str | None, day: str | None) -> tuple | None:
    """(slot_date, slot) to render, or None when nothing has been generated.

    The league row is written for every slot even when nothing qualified, so
    "no row" unambiguously means "not generated yet" -- which is what makes
    falling back to an older slot correct rather than a guess.
    """
    # One query where there used to be up to three, because every statement
    # is a full round trip. The old cascade -- exact (date, slot) asked for,
    # then that slot today, then whatever is newest -- becomes ORDER BY
    # tiers over the same league rows. coalesce(), because comparing against
    # a NULL parameter yields NULL, and Postgres sorts NULLs FIRST under
    # DESC -- which would rank rows nobody asked for above real matches.
    today = datetime.now(ZoneInfo(BRIEF_TZ)).date()
    row = session.execute(
        text("""
            select slot_date, slot from brief_sections
            where team_code = 'LEAGUE'
            order by coalesce(slot_date = :day and slot = :slot, false) desc,
                     coalesce(slot_date = :today and slot = :slot, false) desc,
                     generated_at desc
            limit 1
        """),
        {"day": day, "slot": slot, "today": today},
    ).first()
    if not row:
        return None
    # Stale only on the newest-fallback tier, exactly as before: a reader who
    # explicitly opened a back number asked for that date, and today's slot
    # is current by definition. Flagged so the client can say "showing last
    # night's brief" instead of implying it is live.
    exact = day is not None and row.slot_date.isoformat() == day and row.slot == slot
    todays = row.slot_date == today and row.slot == slot
    is_stale = not exact and not todays and row.slot_date != today
    return (row.slot_date, row.slot, is_stale)


def _stories_for(session, cluster_ids: list[str]) -> dict[str, dict]:
    """The stories behind a section, one row each rather than one per article.

    Grouped deliberately. A big story carries sixteen near-identical
    headlines, and listing all sixteen reads as a bug -- what a reader wants
    is "Lakers sold, 16 outlets" with the option to open whoever broke it.
    So this collapses to the story and keeps the outlet COUNT, which is the
    corroboration signal, plus the earliest article as the way in.
    """
    if not cluster_ids:
        return {}
    rows = session.execute(
        text("""
            select sm.story_id,
                   coalesce(s.summary_title, s.title) as headline,
                   count(distinct a.outlet_id) as outlet_count,
                   min(a.effective_at) as first_at,
                   (array_agg(a.url order by a.effective_at))[1] as lead_url,
                   (array_agg(o.name order by a.effective_at))[1] as lead_outlet,
                   array_agg(distinct o.name) as outlets
            from story_members sm
            join stories s on s.id = sm.story_id
            join articles a on a.id = sm.article_id
            join outlets o on o.id = a.outlet_id
            where sm.story_id in :ids
            group by sm.story_id, s.summary_title, s.title
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": cluster_ids},
    ).all()
    return {
        str(r.story_id): {
            "id": str(r.story_id),
            "headline": r.headline,
            "outlet_count": r.outlet_count,
            "first_at": r.first_at.isoformat(),
            "lead_outlet": r.lead_outlet,
            "lead_url": r.lead_url,
            "outlets": sorted(r.outlets),
        }
        for r in rows
    }


@app.get("/api/brief")
def api_brief(
    viewer: Annotated[dict | None, Depends(optional_user)],
    local_hour: int = 12,
    slot: str | None = None,
    date: str | None = None,
    all_slots: int = 0,
) -> dict:
    """One reader's brief, assembled from pre-written sections.

    Nothing is generated here. The league section plus the reader's followed
    teams are looked up and ordered -- which is the whole point of generating
    per team: ten thousand Lakers fans read one generation.

    all_slots=1 bundles every edition of the day into one response under
    `editions`, each in this same shape. The page used to fetch the other
    two editions as background requests -- three trips reading the same
    day_rows this handler already holds and throwing two thirds away.
    """
    with Session() as session:
        # No explicit slot means "whatever this reader should be seeing now",
        # decided from THEIR clock -- not the server's, and not Eastern.
        wanted = slot or _preferred_slot(local_hour)
        resolved = _resolve_slot(session, wanted, date or None)
        if resolved is None:
            return {
                "slot": None,
                "sections": [],
                "available_slots": [],
                "following": [],
                "omitted_team_count": 0,
                "is_stale": False,
            }
        slot_date, chosen, is_stale = resolved

        follows: list[str] = []
        if viewer:
            follows = [
                r[0]
                for r in session.execute(
                    text("select team_code from user_teams where user_id = :u"),
                    {"u": viewer["sub"]},
                )
            ]

        # The whole day in one query, split in Python: the chosen slot's
        # sections and the available_slots strip used to be two statements
        # against this same small table, and each statement is a full round
        # trip. A day holds at most three slots of ~31 sections.
        day_rows = session.execute(
            text("""
                select b.slot, b.team_code, b.scope, b.body_md, b.word_count,
                       b.is_major, b.cluster_ids, b.generated_at, t.name
                from brief_sections b
                join teams t on t.code = b.team_code
                where b.slot_date = :d
                order by b.max_importance desc
            """),
            {"d": slot_date},
        ).all()
        follow_set = set(follows)

        def pick(slot_rows) -> tuple[list, int]:
            """Which sections one edition shows this reader, plus the count
            dropped. Split from rendering so every requested edition is
            picked BEFORE one stories query hydrates them all."""
            league = next((r for r in slot_rows if r.team_code == "LEAGUE"), None)
            # slot_rows arrive ordered by max_importance desc, so filtering
            # in place keeps "the team with the biggest news first" -- which
            # is the order the reader should get, not the order they
            # followed in.
            ordered = [r for r in slot_rows if r.team_code in follow_set]

            kept = [league] if league else []
            seen: set[str] = set(league.cluster_ids or []) if league else set()
            omitted = 0
            cap = BRIEF_MAX_RENDERED_SECTIONS - len(kept)
            for row in ordered:
                ids = set(row.cluster_ids or [])
                # A team section carrying nothing the reader has not already
                # read is noise. Sections are pre-written prose, so a story
                # cannot be surgically removed -- dropping the whole
                # redundant section is the honest move.
                if ids and ids <= seen:
                    omitted += 1
                    continue
                if len(kept) - (1 if league else 0) >= cap and not row.is_major:
                    omitted += 1
                    continue
                kept.append(row)
                seen |= ids
            return kept, omitted

        slots_to_render = sorted({r.slot for r in day_rows}) if all_slots else [chosen]
        picked = {
            s: pick([r for r in day_rows if r.slot == s]) for s in slots_to_render
        }

        # One hydration for every edition in the response -- per-slot queries
        # here would hand back the round trips the day_rows merge removed.
        all_ids = sorted(
            {
                i
                for kept, _ in picked.values()
                for r in kept
                for i in (r.cluster_ids or [])
            }
        )
        stories = _stories_for(session, all_ids)

        # From the same day_rows fetch as the sections -- the league row is
        # written every slot, so it is the reliable one-per-slot marker.
        available = [
            {
                "slot": r.slot,
                "generated_at": r.generated_at.isoformat(),
                "word_count": r.word_count,
                "first_line": (r.body_md or "").split(". ")[0][:160],
            }
            for r in day_rows
            if r.team_code == "LEAGUE"
        ]

        def render(slot_name: str, kept: list, omitted: int, stale: bool) -> dict:
            return {
                "slot": slot_name,
                "slot_date": slot_date.isoformat(),
                "generated_at": kept[0].generated_at.isoformat() if kept else None,
                "is_stale": stale,
                "sections": [
                    {
                        "scope": r.scope,
                        "team": None if r.team_code == "LEAGUE" else r.team_code,
                        "team_name": None if r.team_code == "LEAGUE" else r.name,
                        "body_md": r.body_md,
                        "word_count": r.word_count,
                        "is_major": r.is_major,
                        # One entry per STORY, not per article: the section's
                        # own cluster order is kept, so what the brief
                        # mentions first is what a reader sees first
                        # underneath it.
                        "stories": [
                            stories[cid]
                            for cid in (r.cluster_ids or [])
                            if cid in stories
                        ],
                    }
                    for r in kept
                ],
                "available_slots": available,
                "following": follows,
                "omitted_team_count": omitted,
            }

        today = datetime.now(ZoneInfo(BRIEF_TZ)).date()
        editions = {
            s: render(
                s,
                *picked[s],
                # The resolved slot keeps _resolve_slot's verdict; its
                # siblings share the day, so staleness is just "not today".
                is_stale if s == chosen else slot_date != today,
            )
            for s in slots_to_render
        }

        # A COPY, or the response would contain itself: editions[chosen] is
        # also the body, and JSON has no cycles.
        body = dict(editions[chosen])
        if all_slots:
            body["editions"] = editions
        return body


@app.get("/api/user-teams")
def api_user_teams(viewer: Annotated[dict, Depends(current_user)]) -> list[str]:
    with Session() as session:
        return [
            r[0]
            for r in session.execute(
                text("""
                    select ut.team_code from user_teams ut
                    join teams t on t.code = ut.team_code
                    where ut.user_id = :u order by t.sort_order
                """),
                {"u": viewer["sub"]},
            )
        ]


@app.put("/api/user-teams")
def api_set_user_teams(
    body: TeamsIn, viewer: Annotated[dict, Depends(current_user)]
) -> dict:
    """Replace the whole follow set. No cap on how many.

    Following twelve teams costs nothing to generate -- sections already exist
    -- so the limit that keeps a brief readable belongs at render time, not
    here.
    """
    codes = [c.strip().upper() for c in body.codes if c and c.strip()]
    with Session() as session:
        # Two statements, not one per team: this fires on every toggle in the
        # picker, and each statement is a full round trip to the database --
        # the loop version cost ~15 round trips for a 12-team save, over a
        # second on a residential connection. Validation is folded into the
        # INSERT's join against teams, and RETURNING carries back what stuck.
        #
        # Deliberately NOT one delete-and-insert CTE: data-modifying CTEs
        # share a snapshot, so the INSERT cannot see the DELETE's effect and
        # re-adding a team the reader already follows collides with the
        # not-yet-deleted row.
        session.execute(
            text("delete from user_teams where user_id = :u"), {"u": viewer["sub"]}
        )
        kept = [
            r[0]
            for r in session.execute(
                text("""
                    insert into user_teams (id, user_id, team_code)
                    select gen_random_uuid(), :u, t.code
                    from teams t
                    where t.kind = 'team'
                      and t.code = any(cast(:codes as text[]))
                    returning team_code
                """),
                {"u": viewer["sub"], "codes": codes},
            )
        ]
        session.commit()
        return {"following": kept}


# Serve the built React app at the root: the brief IS the site now, so the
# milestone-1 HTML page that used to live at "/" is gone. /status and /healthz
# survive because they are operational surfaces rather than product, and both
# are declared above this mount -- which must stay last, since a mount matches
# every path beneath it and anything declared after would be unreachable.
_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST.is_dir():
    # Every client-side route needs an entry here. StaticFiles only resolves
    # real files, so /login is a 404 on hard refresh without this. Listed
    # explicitly rather than as a catch-all so a genuinely wrong URL still
    # 404s instead of silently rendering the app.
    _SPA_ROUTES = [
        "/login",
        "/signup",
        "/settings",
        "/stories",
        "/stories/c/{category}",
        "/stories/t/{team}",
        "/stories/t/{team}/c/{category}",
        "/story/{story_id}",
        "/favorites",
        "/u/{handle}",
    ]

    def _serve_index() -> str:
        return (_DIST / "index.html").read_text(encoding="utf-8")

    for _route in _SPA_ROUTES:
        # Registered BEFORE the mount on purpose -- routes match in
        # declaration order, and the mount would otherwise swallow these.
        app.get(_route, response_class=HTMLResponse)(_serve_index)

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
