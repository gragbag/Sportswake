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
from datetime import timedelta
from pathlib import Path
from typing import Annotated

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

app = FastAPI(title="Presswake")

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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    with Session() as session:
        total = session.scalar(select(func.count()).select_from(Article))
        recent = (
            session.query(Article, Outlet)
            .join(Outlet, Article.outlet_id == Outlet.id)
            .order_by(Article.published_at.desc().nullslast())
            .limit(25)
            .all()
        )

    items = "".join(
        f'<li><a href="{html.escape(a.url)}">{html.escape(a.headline)}</a><br>'
        f"<span>{html.escape(o.name)}"
        f"{' &middot; ' + a.published_at.strftime('%b %d, %H:%M UTC') if a.published_at else ''}"
        f"</span></li>"
        for a, o in recent
    )

    empty = "<p>No articles yet. Run the worker.</p>"

    return f"""<!doctype html><meta charset="utf-8">
<title>Crosscut</title><style>{STYLE}</style>
<h1>Crosscut</h1>
<p class="sub">{total:,} articles in the corpus &middot; <a href="/status">status</a></p>
{f"<ol>{items}</ol>" if recent else empty}"""


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


SPARK_BUCKETS = 10

# The select list every card needs. Shared so the feed and the favorites list
# cannot drift into returning different shapes for the same component.
_CARD_COLUMNS = """
    s.id, s.title, s.summary_title, s.summary_subhead,
    count(*) as article_count,
    count(distinct a.outlet_id) as outlet_count,
    min(coalesce(a.published_at, a.first_seen_at)) as first_at,
    max(coalesce(a.published_at, a.first_seen_at)) as last_at
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
                   coalesce(a.published_at, a.first_seen_at) as pub_at
            from story_members sm
            join articles a on a.id = sm.article_id
            join outlets o on o.id = a.outlet_id
            where sm.story_id in :ids
            order by pub_at
        """).bindparams(bindparam("ids", expanding=True)),
        {"ids": [r.id for r in rows]},
    ).all()

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
            }
        )
    return out


@app.get("/api/stories")
def api_stories(limit: int = 24) -> list[dict]:
    """Stories worth rendering, most-covered first.

    Singletons are excluded here, not from the corpus -- they are what supports
    "only one outlet covered this", so they stay in the database and stay out
    of the feed.
    """
    with Session() as session:
        rows = session.execute(
            text(f"""
                select {_CARD_COLUMNS}
                from stories s
                join story_members sm on sm.story_id = s.id
                join articles a on a.id = sm.article_id
                group by s.id
                having count(distinct a.outlet_id) >= 2
                order by count(distinct a.outlet_id) desc, max(
                    coalesce(a.published_at, a.first_seen_at)) desc
                limit :limit
            """),
            {"limit": limit},
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
                       c.created_at, c.edited_at,
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
                  and c.status = 'visible'
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
    return {
        "id": str(r.id),
        # The author's uuid, not their email: an email address is personal
        # data and does not belong in a public payload. The frontend needs
        # it only to mark a comment as its own.
        "user_id": str(r.user_id),
        # Resolved server-side so every surface agrees on what to call
        # someone, rather than each component reimplementing the fallback.
        "author": r.username or derive_handle(str(r.user_id)),
        "body": r.body,
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
                insert into comments (id, user_id, story_id, body, status)
                values (gen_random_uuid(), :uid, :sid, :body, :status)
                returning id, created_at
            """),
            {
                "uid": user["sub"],
                "sid": story_id,
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
        # The author is told what happened to their own comment. Silently
        # storing a removed comment and rendering nothing is what makes
        # moderation feel like a bug.
        "status": verdict.status,
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
                       min(coalesce(a.published_at, a.first_seen_at)) as first_at,
                       max(coalesce(a.published_at, a.first_seen_at)) as last_at
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
                       coalesce(a.published_at, a.first_seen_at) as pub_at
                from story_members sm
                join articles a on a.id = sm.article_id
                join outlets o on o.id = a.outlet_id
                where sm.story_id = :sid
                order by pub_at
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


# Serve the built React app, if it has been built. Mounted at /app rather than
# "/" so the existing server-rendered pages keep working -- move it to "/" once
# React replaces them. Must be registered last: a mount matches every path
# beneath it, so anything declared after it would be unreachable.
_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST.is_dir():
    # Every client-side route needs an entry here. StaticFiles only resolves
    # real files, so /app/login is a 404 on hard refresh without this.
    # Listed explicitly rather than as a catch-all so a genuinely wrong URL
    # still 404s instead of silently rendering the app.
    _SPA_ROUTES = [
        "/app/story/{story_id}",
        "/app/login",
        "/app/signup",
        "/app/favorites",
        "/app/settings",
        "/app/u/{handle}",
    ]

    def _serve_index() -> str:
        return (_DIST / "index.html").read_text(encoding="utf-8")

    for _route in _SPA_ROUTES:
        # Registered BEFORE the mount on purpose -- routes match in
        # declaration order, and the mount would otherwise swallow these.
        app.get(_route, response_class=HTMLResponse)(_serve_index)

    app.mount("/app", StaticFiles(directory=_DIST, html=True), name="frontend")
