"""Throwaway: does article body text improve clustering separation?

    python scripts/body_experiment.py michigan
    python scripts/body_experiment.py gaza

Fetches each matching article's page, extracts the body, and compares
neighbour similarity with and without a body excerpt.

What you are looking for: same-story pairs go UP, different-story pairs go
DOWN. If that does not happen, do not build the crawler.

Needs: pip install trafilatura
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import (
    Article,
    Outlet,
    make_engine,
    make_session_factory,
)
from worker.embed import article_text, embed_texts, strip_html

UA = {"User-Agent": "Presswake/0.1 (+https://github.com/gragbag/Presswake)"}
LIMIT = 25  # keep the experiment small and polite
EXCERPT_CHARS = 1500
TIMEOUT = 15


def _jsonld_body(html: str) -> str | None:
    """Many outlets publish the article text as JSON-LD articleBody. Free,
    structured, no ML -- always worth trying before a real extractor."""
    for m in re.finditer(
        r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.DOTALL
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                body = node.get("articleBody")
                if isinstance(body, str) and len(body) > 200:
                    return body
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


def fetch_body(url: str) -> tuple[str, str]:
    """Returns (excerpt, source). Source tells you which method worked."""
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    html = r.text

    body, source = _jsonld_body(html), "jsonld"
    if not body:
        import trafilatura

        body = trafilatura.extract(html, include_comments=False, include_tables=False)
        source = "trafilatura"

    return strip_html(body or "")[:EXCERPT_CHARS], source


def main() -> int:
    term = " ".join(sys.argv[1:]).strip()
    if not term:
        print("usage: python scripts/body_experiment.py <term>")
        return 1

    Session = make_session_factory(make_engine())
    with Session() as session:
        rows = (
            session.query(Article, Outlet)
            .join(Outlet, Outlet.id == Article.outlet_id)
            .filter(Article.headline.ilike(f"%{term}%"))
            .order_by(Article.published_at.desc().nullslast())
            .limit(LIMIT)
            .all()
        )

    if len(rows) < 3:
        print(f"only {len(rows)} articles match {term!r}")
        return 1

    print(f"fetching {len(rows)} article pages...")
    bodies: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_body, a.url): a.id for a, _ in rows}
        for fut in as_completed(futures):
            aid = futures[fut]
            try:
                bodies[aid] = fut.result()
            except Exception as exc:  # noqa: BLE001 - one bad page must not kill the batch
                bodies[aid] = ("", f"ERR {type(exc).__name__}")

    ok = [a for a, _ in rows if bodies[a.id][0]]
    lens = [len(bodies[a.id][0]) for a in ok]
    print(
        f"extracted {len(ok)}/{len(rows)}  "
        f"mean excerpt {sum(lens) // max(len(lens), 1)} chars\n"
    )

    usable = [(a, o) for a, o in rows if bodies[a.id][0]]
    if len(usable) < 3:
        print("too few successful extractions to compare")
        return 1

    old_texts = [article_text(a) for a, _ in usable]
    new_texts = [f"{article_text(a)}\n{bodies[a.id][0]}" for a, _ in usable]
    old_vecs = embed_texts(old_texts)
    new_vecs = embed_texts(new_texts)

    def dot(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    seed, seed_outlet = usable[0]
    print(f"SEED  [{seed_outlet.name}]  {seed.headline[:78]}\n")
    print(f"  {'old':>5}  {'new':>5}  {'delta':>6}  {'source':<12} outlet / headline")

    scored = []
    for i, (a, o) in enumerate(usable[1:], start=1):
        old = dot(old_vecs[0], old_vecs[i])
        new = dot(new_vecs[0], new_vecs[i])
        scored.append((new, old, a, o))
    scored.sort(reverse=True, key=lambda r: r[0])

    for new, old, a, o in scored:
        src = bodies[a.id][1]
        print(
            f"  {old:>5.3f}  {new:>5.3f}  {new - old:>+6.3f}  {src:<12} "
            f"[{o.name[:16]:<16}] {a.headline[:52]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
