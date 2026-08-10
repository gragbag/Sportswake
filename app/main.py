"""Milestone 1 app: proves the corpus exists and is growing.

Deliberately plain. Real design work happens at milestone 4, when there are
story pages worth designing. This page has one job: show that the worker ran
and the number went up.
"""

from __future__ import annotations

import html
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import bindparam, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import current_user
from common.models import (
    Article,
    FetchRun,
    Outlet,
    Story,
    make_engine,
    make_session_factory,
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
    ]

    def _serve_index() -> str:
        return (_DIST / "index.html").read_text(encoding="utf-8")

    for _route in _SPA_ROUTES:
        # Registered BEFORE the mount on purpose -- routes match in
        # declaration order, and the mount would otherwise swallow these.
        app.get(_route, response_class=HTMLResponse)(_serve_index)

    app.mount("/app", StaticFiles(directory=_DIST, html=True), name="frontend")
