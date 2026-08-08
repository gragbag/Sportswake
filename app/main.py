"""Milestone 1 app: proves the corpus exists and is growing.

Deliberately plain. Real design work happens at milestone 4, when there are
story pages worth designing. This page has one job: show that the worker ran
and the number went up.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import bindparam, func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


@app.get("/api/stories")
def api_stories(limit: int = 24) -> list[dict]:
    """Stories worth rendering, most-covered first.

    Singletons are excluded here, not from the corpus -- they are what supports
    "only one outlet covered this", so they stay in the database and stay out
    of the feed.

    The sparkline is bucketed server-side. Sending every member timestamp would
    be ~2,400 ISO strings for one page of cards to draw ten bars from.
    """
    with Session() as session:
        rows = session.execute(
            text("""
                select s.id, s.title, s.summary_title, s.summary_subhead,
                       count(*) as article_count,
                       count(distinct a.outlet_id) as outlet_count,
                       min(coalesce(a.published_at, a.first_seen_at)) as first_at,
                       max(coalesce(a.published_at, a.first_seen_at)) as last_at
                from stories s
                join story_members sm on sm.story_id = s.id
                join articles a on a.id = sm.article_id
                group by s.id, s.title, s.summary_title, s.summary_subhead
                having count(distinct a.outlet_id) >= 2
                order by count(distinct a.outlet_id) desc, max(
                    coalesce(a.published_at, a.first_seen_at)) desc
                limit :limit
            """),
            {"limit": limit},
        ).all()

        if not rows:
            return []

        members = session.execute(
            text("""
                select sm.story_id, o.name,
                       coalesce(a.published_at, a.first_seen_at) as t
                from story_members sm
                join articles a on a.id = sm.article_id
                join outlets o on o.id = a.outlet_id
                where sm.story_id in :ids
                order by t
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
                # Nullable by design: the card falls back to the seed title and
                # shows no AI label when these are absent. Bullets/people stay
                # out of this payload -- they belong to the story page.
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


# Serve the built React app, if it has been built. Mounted at /app rather than
# "/" so the existing server-rendered pages keep working -- move it to "/" once
# React replaces them. Must be registered last: a mount matches every path
# beneath it, so anything declared after it would be unreachable.
_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/app", StaticFiles(directory=_DIST, html=True), name="frontend")
