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
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import (  # noqa: E402
    Article, FetchRun, Outlet, make_engine, make_session_factory,
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
{f'<ol>{items}</ol>' if recent else empty}"""


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
        f"<td class=\"{'err' if last and last.status == 'error' else ''}\">"
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