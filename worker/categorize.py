"""Assign categories to stories.

    python -m worker.categorize            (make categorize)
    python -m worker.categorize --dry-run

Deliberately NOT folded into worker/summarize.py, even though that already
makes one LLM call per story. Summaries only cover stories with 5+ outlets,
while the feed shows everything with 2+ -- riding along would leave most of
the feed untagged. It also uses the small model, whose Groq rate limit is a
separate pool, so backfilling the whole corpus cannot starve summarization.

The category list is read from the database rather than hardcoded. That is
the whole payoff of storing the taxonomy as rows: adding a ninth category is
an INSERT, and both the prompt and the validator pick it up on the next run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI, RateLimitError
from sqlalchemy import text

from common.config import (
    CATEGORY_BATCH_LIMIT,
    CATEGORY_MAX,
    CATEGORY_MIN_OUTLETS,
    CATEGORY_MODEL,
    CATEGORY_PACE_SECONDS,
    GROQ_API_KEY,
    SUMMARY_BASE_URL,
)
from common.models import make_engine, make_session_factory

# "JSON" must appear literally -- Groq's json_object mode rejects the
# request otherwise.
_PROMPT = """\
Assign news categories to a story. You are given its headline and how
several outlets covered it.

Choose from exactly these categories:
{catalog}

Reply with JSON only: {{"categories": ["slug", ...]}}

Give ONE category. Add a second only when the story is genuinely central to
both -- a tariff announcement is politics and business; a football transfer
is only sports. Never more than {max_n}. Use the slugs exactly as written.
If nothing fits, reply with an empty list rather than forcing a choice.
"""


def get_client() -> OpenAI | None:
    """None when no key is configured -- categorisation is off, not broken."""
    if not GROQ_API_KEY:
        return None
    return OpenAI(api_key=GROQ_API_KEY, base_url=SUMMARY_BASE_URL)


def load_catalog(session) -> dict[str, str]:
    """{slug: label} in tab order, straight from the database."""
    rows = session.execute(
        text("select slug, label from categories order by sort_order")
    ).all()
    return {r.slug: r.label for r in rows}


def stories_needing_categories(session, limit: int) -> list[tuple[str, str]]:
    """(story_id, title) for feed-eligible stories with no categories yet.

    Ordered by outlet count so the most-covered stories get tagged first --
    if a run is cut short, the tabs still have their most visible content.
    """
    rows = session.execute(
        text("""
            select s.id, coalesce(s.summary_title, s.title) as title
            from stories s
            join story_members sm on sm.story_id = s.id
            join articles a on a.id = sm.article_id
            where not exists (
                select 1 from story_categories sc where sc.story_id = s.id
            )
            group by s.id, s.title, s.summary_title
            having count(distinct a.outlet_id) >= :min_outlets
            order by count(distinct a.outlet_id) desc
            limit :limit
        """),
        {"min_outlets": CATEGORY_MIN_OUTLETS, "limit": limit},
    ).all()
    return [(r.id, r.title) for r in rows]


def build_input(session, story_id: str, title: str) -> str:
    """Headline plus a few outlet headlines. Small on purpose.

    One headline per outlet is enough signal to place a story in a taxonomy
    of eight; sending thirty would cost ten times the tokens to answer the
    same question.
    """
    rows = session.execute(
        text("""
            select distinct on (a.outlet_id) o.name, a.headline
            from story_members sm
            join articles a on a.id = sm.article_id
            join outlets o on o.id = a.outlet_id
            where sm.story_id = :sid
            order by a.outlet_id, coalesce(a.published_at, a.first_seen_at)
            limit 5
        """),
        {"sid": story_id},
    ).all()
    lines = [f"{r.name}: {r.headline}" for r in rows]
    return f"{title}\n\n" + "\n".join(lines)


def classify(client: OpenAI, catalog: dict[str, str], body: str) -> list[str] | None:
    """Valid slugs in rank order, or None if the model gave nothing usable.

    Invalid slugs are DROPPED rather than failing the whole call -- the same
    treatment summarize.py gives hallucinated names. A model that invents
    "geopolitics" alongside a good "world" should not cost us both.
    """
    catalog_text = "\n".join(f"  {slug} - {label}" for slug, label in catalog.items())
    resp = client.chat.completions.create(
        model=CATEGORY_MODEL,
        temperature=0,
        max_tokens=60,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": _PROMPT.format(catalog=catalog_text, max_n=CATEGORY_MAX),
            },
            {"role": "user", "content": body},
        ],
    )
    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("categories"), list):
        return None

    seen: list[str] = []
    for item in data["categories"]:
        if isinstance(item, str) and item in catalog and item not in seen:
            seen.append(item)
    return seen[:CATEGORY_MAX]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=CATEGORY_BATCH_LIMIT)
    args = parser.parse_args()

    client = get_client()
    if client is None:
        # Exit 0: no key means the feature is off, not broken.
        print("GROQ_API_KEY not set; skipping categorisation")
        return 0

    engine = make_engine()
    Session = make_session_factory(engine)

    with Session() as session:
        catalog = load_catalog(session)
        if not catalog:
            print("no categories seeded; run migrations first")
            return 0

        pending = stories_needing_categories(session, args.limit)
        print(f"{len(pending)} stories need categories")

        tagged = skipped = 0
        for story_id, title in pending:
            body = build_input(session, story_id, title)
            try:
                slugs = classify(client, catalog, body)
            except RateLimitError:
                # Stop the run, not just this story. The next one resumes
                # exactly here because nothing below got a row.
                print("rate limited -- stopping this run")
                break

            if not slugs:
                # An empty result is a real answer: the story fits nothing.
                # Leaving it untagged is how we find out whether these eight
                # are the right eight.
                skipped += 1
                print(f"  no category: {title[:56]}")
            elif args.dry_run:
                print(f"  {','.join(slugs):<28} {title[:52]}")
            else:
                for rank, slug in enumerate(slugs):
                    session.execute(
                        text("""
                            insert into story_categories
                                (story_id, category_slug, rank)
                            values (:sid, :slug, :rank)
                            on conflict (story_id, category_slug) do nothing
                        """),
                        {"sid": story_id, "slug": slug, "rank": rank},
                    )
                session.commit()
                tagged += 1

            time.sleep(CATEGORY_PACE_SECONDS)

        verb = "would tag" if args.dry_run else "tagged"
        print(f"\n{verb} {tagged}, no category {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
