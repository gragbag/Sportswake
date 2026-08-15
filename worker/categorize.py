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
from typing import NamedTuple

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
    PLACE_MAX,
    SUMMARY_BASE_URL,
)
from common.models import make_engine, make_session_factory

# "JSON" must appear literally -- Groq's json_object mode rejects the
# request otherwise.
_PROMPT = """\
Tag a news story. You are given its headline and how several outlets
covered it.

Choose categories from exactly this list:
{catalog}

Also say WHERE the story happens, as "places":
  - a country, as its ISO 3166-1 alpha-2 code (GB, IN, US, BR)
  - or one of these when no single country fits:
{regions}
  - GLOBAL only when the story genuinely spans continents. An event
    crossing several countries in one part of the world is that region,
    not GLOBAL.

Always prefer the country. A region is for stories no single country is
the subject of -- an attack inside Ukraine is UA, not EUROPE, even when
other countries react to it.

Reply with JSON only:
  {{"categories": ["slug", ...], "places": ["code", ...]}}

Give ONE category, and a second only when the story is genuinely central to
both -- a tariff announcement is politics and business; a football transfer
is only sports. Places work the same way: one, or two when the story is
equally about both -- US-China trade talks are US and CN.

Never more than {max_n} of either. Use the slugs and codes exactly as
written. Prefer an empty list over forcing a choice.
"""


def get_client() -> OpenAI | None:
    """None when no key is configured -- categorisation is off, not broken."""
    if not GROQ_API_KEY:
        return None
    return OpenAI(api_key=GROQ_API_KEY, base_url=SUMMARY_BASE_URL)


def load_catalog(session) -> dict[str, str]:
    """{slug: "Label -- what belongs here"} in tab order, from the database.

    The description is joined in rather than returned separately because every
    caller wants both: classify() renders them into the prompt, and nothing
    else reads the catalog at all.
    """
    rows = session.execute(
        text("select slug, label, description from categories order by sort_order")
    ).all()
    return {r.slug: f"{r.label} -- {r.description}" for r in rows}


def load_places(session) -> tuple[set[str], list[str]]:
    """(every valid code, the region/global codes only).

    The full set is the validator; only the second list reaches the prompt.
    Sending all ~130 countries would cost roughly 1,500 tokens per call
    against this model's 6,000 TPM ceiling -- about four stories a minute.
    The model already knows ISO 3166-1 alpha-2, so it is asked for a code
    and checked afterwards, which is the opposite of how categories work.
    """
    rows = session.execute(
        text("select code, kind from places order by sort_order")
    ).all()
    return (
        {r.code for r in rows},
        [r.code for r in rows if r.kind != "country"],
    )


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


class Tags(NamedTuple):
    """One classify() result.

    `dropped` is here because the country list is curated. From inside this
    function a real code the table happens not to hold is indistinguishable
    from a hallucination, and only a person reading the output can tell them
    apart -- so they get printed rather than discarded silently. That is the
    whole mitigation for choosing a curated list over the full ISO 249.
    """

    categories: list[str]
    places: list[str]
    dropped: list[str]


# Codes the model reaches for that are not what this table calls them. All
# three are things it is right to emit and wrong to reject: EU and UK are
# "exceptionally reserved" in ISO 3166-1 rather than the official codes (GB
# is), and USA is alpha-3. Deliberately NOT here: ME, which reads as Middle
# East but is Montenegro -- aliasing it would silently mistag a country.
_ALIASES = {"EU": "EUROPE", "UK": "GB", "USA": "US"}


def _pick(items: object, valid: set[str], limit: int) -> tuple[list[str], list[str]]:
    """(known values in order, unknown ones). Never raises.

    Anything that is not a list of strings yields nothing rather than an
    exception: the model controls this value, so it is input, not data.
    """
    kept: list[str] = []
    dropped: list[str] = []
    if not isinstance(items, list):
        return kept, dropped
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip()
        value = _ALIASES.get(value, value)
        if value in valid:
            if value not in kept:
                kept.append(value)
        elif value and value not in dropped:
            dropped.append(value)
    return kept[:limit], dropped


def classify(
    client: OpenAI,
    catalog: dict[str, str],
    place_codes: set[str],
    regions: list[str],
    body: str,
) -> Tags | None:
    """Valid slugs and place codes in rank order, or None if nothing landed.

    Invalid values are DROPPED rather than failing the whole call -- the same
    treatment summarize.py gives hallucinated names. A model that invents
    "geopolitics" alongside a good "world" should not cost us both, and the
    two lists are validated independently for the same reason.
    """
    catalog_text = "\n".join(f"  {slug} - {label}" for slug, label in catalog.items())
    resp = client.chat.completions.create(
        model=CATEGORY_MODEL,
        temperature=0,
        # Up from 60: the reply carries a second list now.
        max_tokens=100,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": _PROMPT.format(
                    catalog=catalog_text,
                    regions="    " + "  ".join(regions),
                    max_n=CATEGORY_MAX,
                ),
            },
            {"role": "user", "content": body},
        ],
    )
    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    cats, _ = _pick(data.get("categories"), set(catalog), CATEGORY_MAX)
    places, dropped = _pick(data.get("places"), place_codes, PLACE_MAX)
    if not cats and not places:
        return None
    return Tags(cats, places, dropped)


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
        place_codes, regions = load_places(session)
        if not place_codes:
            print("no places seeded; run migrations first")
            return 0

        pending = stories_needing_categories(session, args.limit)
        print(f"{len(pending)} stories need categories")

        tagged = skipped = 0
        # Union across the run, not per story: a code the curated list is
        # missing shows up on every story about that country, and one line
        # at the end is what makes the gap actionable.
        unknown: set[str] = set()
        for story_id, title in pending:
            body = build_input(session, story_id, title)
            try:
                tags = classify(client, catalog, place_codes, regions, body)
            except RateLimitError:
                # Stop the run, not just this story. The next one resumes
                # exactly here because nothing below got a row.
                print("rate limited -- stopping this run")
                break

            if tags is None:
                # An empty result is a real answer: the story fits nothing.
                # Leaving it untagged is how we find out whether these eight
                # are the right eight.
                skipped += 1
                print(f"  no category: {title[:56]}")
                time.sleep(CATEGORY_PACE_SECONDS)
                continue

            unknown.update(tags.dropped)
            shown = f"{','.join(tags.categories)} @ {','.join(tags.places) or '-'}"
            if args.dry_run:
                # Counted here too, or the summary reads "would tag 0" after
                # printing a screen of tags it would have written.
                tagged += 1
                print(f"  {shown:<40} {title[:44]}")
            else:
                for rank, slug in enumerate(tags.categories):
                    session.execute(
                        text("""
                            insert into story_categories
                                (story_id, category_slug, rank)
                            values (:sid, :slug, :rank)
                            on conflict (story_id, category_slug) do nothing
                        """),
                        {"sid": story_id, "slug": slug, "rank": rank},
                    )
                for rank, code in enumerate(tags.places):
                    session.execute(
                        text("""
                            insert into story_places (story_id, place_code, rank)
                            values (:sid, :code, :rank)
                            on conflict (story_id, place_code) do nothing
                        """),
                        {"sid": story_id, "code": code, "rank": rank},
                    )
                # One commit for both, so a story is never half-tagged --
                # stories_needing_categories keys off story_categories alone.
                session.commit()
                tagged += 1

            time.sleep(CATEGORY_PACE_SECONDS)

        verb = "would tag" if args.dry_run else "tagged"
        print(f"\n{verb} {tagged}, no category {skipped}")
        if unknown:
            print(
                f"rejected {len(unknown)} unknown place code(s): "
                f"{', '.join(sorted(unknown))}\n"
                "  Real ones are gaps in the curated list -- add with an "
                "INSERT into places, no migration needed."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
