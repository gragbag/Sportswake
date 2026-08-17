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
    CATEGORY_MAX_ATTEMPTS,
    CATEGORY_MIN_OUTLETS,
    CATEGORY_MODEL,
    CATEGORY_PACE_SECONDS,
    CATEGORY_REGEN_GROWTH,
    GROQ_API_KEY,
    SUMMARY_BASE_URL,
    TEAM_MAX,
)
from common.models import make_engine, make_session_factory
from worker.embed import strip_html

# "JSON" must appear literally -- Groq's json_object mode rejects the
# request otherwise.
_PROMPT = """\
Tag an NBA news story. You are given its headline and how several outlets
covered it.

Choose categories from exactly this list:
{catalog}

Also say WHICH TEAMS the story is about, as "teams":
  - the team's name, written the way people write it: "Phoenix Suns",
    "Indiana Pacers", "Golden State Warriors"
  - or one of these exactly, when no single team is the subject:
{scopes}

Reply with JSON only:
  {{"categories": ["slug", ...], "teams": ["code", ...], "is_rumor": true}}

Give ONE category, and a second only when the story is genuinely both --
a trade that clears cap space is trades and free-agency; a game recap is
only games.

Teams work differently: name EVERY team the story is actually about, up to
{max_n}. A trade has two sides and both belong. A game involves both clubs.
Use LEAGUE only for genuinely league-wide news -- the CBA, expansion, media
rights -- never as a fallback when you are unsure.

Only name a team the text actually supports. If the story never says which
team a player is on, leave it out rather than recalling it -- rosters change
and yours may be out of date.

Set "is_rumor" true when the story reports speculation rather than settled
fact -- talks, interest, a deal someone MAY make, anything attributed to
sources about what might happen. Set it false when the thing has actually
happened: a completed trade, a signed contract, a played game. "Lakers agree
to deal" is false; "Lakers exploring a deal" is true. A brief must name the
outlet and mark the item as reporting when this is true, so when the story is
genuinely between the two, say true.

Use the slugs and codes exactly as written. Prefer an empty list over
forcing a choice.
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


def load_teams(session) -> tuple[set[str], list[str]]:
    """(every valid code, the conference/league codes only).

    The full set is the validator; only the second list reaches the prompt.
    Thirty team codes would fit, unlike the ~130 countries this replaced, but
    they still do not need to be sent: LAL and BOS appear in every box score
    ever written, so the model emits them correctly unprompted. Asking for a
    code and checking it afterwards is the opposite of how categories work,
    where the model is shown the list because the slugs are ours.
    """
    rows = session.execute(
        text("select code, kind from teams order by sort_order")
    ).all()
    return (
        {r.code for r in rows},
        [r.code for r in rows if r.kind != "team"],
    )


def stories_needing_categories(
    session, limit: int, retag: bool = False
) -> list[tuple[str, str]]:
    """(story_id, title) for feed-eligible stories whose tags need writing.

    Three ways in, and the middle one is the reason this is not simply "has
    no story_categories row":

      - never attempted
      - attempted before, and the story has since grown by CATEGORY_REGEN_
        GROWTH. merge_pass folds whole stories into each other, so a set of
        tags describes a member set that no longer exists. summarize has the
        same rule for the same reason.
      - attempted and failed, with attempts left

    Ordered by outlet count so the most-covered stories get tagged first --
    if a run is cut short, the tabs still have their most visible content.
    That ordering is also why the attempt bound matters: without it a story
    the model cannot tag comes back to the FRONT of the queue every run.
    """
    rows = session.execute(
        text("""
            select s.id, coalesce(s.summary_title, s.title) as title
            from stories s
            join story_members sm on sm.story_id = s.id
            join articles a on a.id = sm.article_id
            group by s.id, s.title, s.summary_title,
                     s.categorized_at, s.categorized_outlet_count,
                     s.category_attempts
            having count(distinct a.outlet_id) >= :min_outlets
               and (
                     :retag
                     or s.categorized_outlet_count is null
                     or count(distinct a.outlet_id)
                        >= s.categorized_outlet_count * :growth
                     or (s.categorized_at is null
                         and s.category_attempts < :max_attempts)
                   )
            order by count(distinct a.outlet_id) desc
            limit :limit
        """),
        {
            "min_outlets": CATEGORY_MIN_OUTLETS,
            "growth": CATEGORY_REGEN_GROWTH,
            "max_attempts": CATEGORY_MAX_ATTEMPTS,
            "limit": limit,
            "retag": retag,
        },
    ).all()
    return [(r.id, r.title) for r in rows]


# Enough to carry the team, not enough to carry the article. A team is named
# in the first sentence essentially always -- "Indiana Pacers guard Tyrese
# Haliburton said..." -- so this buys the evidence without paying for the
# whole body.
_LEDE_CHARS = 300


def build_input(session, story_id: str, title: str) -> str:
    """Headline and opening line from each outlet, one per outlet.

    THE LEDE IS NOT OPTIONAL, and it used to be. This function originally
    sent headlines only, sized when the single question was "which of eight
    categories?" -- for which a headline genuinely is enough. Teams arrived
    later (0013) and reused the same input without anyone re-asking whether
    it carried the evidence, and it does not: measured over 71 real tags, the
    team is named in the headlines 59% of the time and in headline+lede 72%.

    That gap is not academic. Eight outlets covered Tyrese Haliburton over
    three days without once naming his team in a headline -- their readers
    already know -- so the model had nothing to read and filled the hole from
    training data, tagging the story SAC because Sacramento drafted him in
    2020 and traded him in 2022. Every one of those articles said "Pacers" in
    its lede. We were throwing the answer away before the model saw it.
    """
    rows = session.execute(
        text("""
            select distinct on (a.outlet_id) o.name, a.headline, a.lede
            from story_members sm
            join articles a on a.id = sm.article_id
            join outlets o on o.id = a.outlet_id
            where sm.story_id = :sid
            order by a.outlet_id, a.effective_at
            limit 5
        """),
        {"sid": story_id},
    ).all()

    lines = []
    for r in rows:
        # Ledes are RSS descriptions and arrive as HTML. strip_html is the
        # canonical cleaner in this pipeline -- the embedder and summarizer
        # both use it, so all three see the same text.
        lede = strip_html(r.lede or "").strip().replace("\n", " ")
        if lede:
            lines.append(f"{r.name}: {r.headline} -- {lede[:_LEDE_CHARS]}")
        else:
            lines.append(f"{r.name}: {r.headline}")
    return f"{title}\n\n" + "\n".join(lines)


class Tags(NamedTuple):
    """One classify() result.

    `dropped` is here because the roster is fixed. From inside this
    function a code the table does not hold is indistinguishable from a
    hallucination, and only a person reading the output can tell them apart.
    They get printed rather than dropped silently -- which is how a genuine
    gap (a relocated franchise, a second league) becomes visible instead of
    quietly costing every story about it.
    """

    categories: list[str]
    teams: list[str]
    dropped: list[str]
    # Speculation rather than settled fact. Decides whether a brief presents
    # the item as reporting and names the outlet, so it is an editorial rule
    # carried as a boolean.
    is_rumor: bool = False


_TEAM_ALIASES = {
    # Codes the model reaches for that are not what this table calls them.
    # Every one is a real abbreviation in circulation: NBA.com uses NOH and
    # NO for New Orleans, box scores vary between PHO and PHX, and BRK is
    # Basketball-Reference's own code for Brooklyn.
    "NO": "NOP", "NOH": "NOP", "PHO": "PHX", "BRK": "BKN",
    "GS": "GSW", "SA": "SAS", "NY": "NYK", "UTAH": "UTA", "WSH": "WAS",
    # Right team, wrong token -- measured, not hypothetical.
    "SUN": "PHX", "CAVS": "CLE", "SIXERS": "PHI", "76ERS": "PHI",
    "BLAZERS": "POR", "WOLVES": "MIN", "MAVS": "DAL", "NUGS": "DEN",
    # Names that are correct in the world but not what this table calls the
    # club. The Clippers are seeded as "LA Clippers" -- their own branding --
    # so a model writing the full city name was being rejected as unknown.
    # This is the cost of asking for names instead of codes, and it is a much
    # cheaper failure than the one it replaced: a rejected name is visible in
    # the run output, whereas a wrong code silently tagged the wrong team.
    "LOS ANGELES CLIPPERS": "LAC", "L.A. CLIPPERS": "LAC",
    "LA LAKERS": "LAL", "L.A. LAKERS": "LAL",
}


def team_aliases(session) -> dict[str, str]:
    """Every string the model might plausibly return -> our canonical code.

    Built from the teams table rather than hardcoded, so adding a club stays
    an INSERT and not a code change.

    This exists because of a measured failure mode: the model reads basketball
    correctly and writes abbreviations badly. Asked for a code it returned SAS
    for a story whose text says "Phoenix Suns" three times, and on a later run
    it offered SUN -- right team, wrong token, both times. Asked for a NAME it
    says "Phoenix Suns", and turning that into PHX becomes a lookup we control
    rather than a guess it makes. Codes are still accepted coming in, because
    a model that volunteers PHX should not be punished for being right.
    """
    # Keyed lower throughout, including the hardcoded half: _pick tries the
    # raw string then the folded one, so a single lowercase table serves both
    # "Phoenix Suns" and a volunteered "PHX".
    out: dict[str, str] = {k.lower(): v for k, v in _TEAM_ALIASES.items()}
    for code, name in session.execute(text("select code, name from teams")):
        words = name.split()
        keys = {code, name, words[-1]}
        if len(words) > 1:
            keys.add(" ".join(words[:-1]))  # Phoenix, Golden State, New York
        if len(words) > 2:
            keys.add(" ".join(words[-2:]))  # Trail Blazers, City Thunder
            # The bare city, which the two-part split above misses for
            # "Portland Trail Blazers". Length-gated so "New" does not become
            # a key -- New York and New Orleans would collide on it and the
            # last row loaded would silently win.
            if len(words[0]) >= 5:
                keys.add(words[0])
        for key in keys:
            out[key.strip().lower()] = code
    return out


def _rumor(value: object) -> bool:
    """Read is_rumor tolerantly, defaulting to false.

    Models return a JSON boolean here almost always, but sometimes the string
    "true". Both are accepted; anything else means the field did not arrive.

    Absent defaults to FALSE rather than true, which is the less obvious
    choice -- mislabelling a rumour as fact is the more dangerous direction.
    The reason is that the field is part of a required schema, so absence is
    rare, while defaulting to true would mark ordinary confirmed news as
    "reported" often enough to dilute the label until it carries no
    information at all. A warning that fires constantly is not a warning. The
    prompt does the real work by telling the model to answer true whenever the
    story genuinely sits between the two.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


def _pick(
    items: object,
    valid: set[str],
    limit: int,
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """(known values in order, unknown ones). Never raises.

    Anything that is not a list of strings yields nothing rather than an
    exception: the model controls this value, so it is input, not data.

    `aliases` is a parameter rather than a module constant read directly:
    this helper validates categories as well as teams, and a team-specific
    rewrite silently applied to category slugs is a bug waiting for someone
    to add a category whose slug collides with an abbreviation.
    """
    kept: list[str] = []
    dropped: list[str] = []
    if not isinstance(items, list):
        return kept, dropped
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if aliases:
            # Exact first, then case-folded: the alias table is keyed lower
            # because the model now returns names ("Phoenix Suns"), while the
            # codes it sometimes still volunteers are upper. One lookup can
            # not serve both without normalising here.
            value = aliases.get(value) or aliases.get(value.lower()) or value
        if value in valid:
            if value not in kept:
                kept.append(value)
        elif value and value not in dropped:
            dropped.append(value)
    return kept[:limit], dropped


def classify(
    client: OpenAI,
    catalog: dict[str, str],
    team_codes: set[str],
    scopes: list[str],
    body: str,
    aliases: dict[str, str] | None = None,
) -> Tags | None:
    """Valid slugs and team codes in rank order, or None if nothing landed.

    Invalid values are DROPPED rather than failing the whole call -- the same
    treatment summarize.py gives hallucinated names. A model that invents
    "geopolitics" alongside a good "world" should not cost us both, and the
    two lists are validated independently for the same reason.
    """
    catalog_text = "\n".join(f"  {slug} - {label}" for slug, label in catalog.items())
    resp = client.chat.completions.create(
        model=CATEGORY_MODEL,
        temperature=0,
        # 60 -> 100 when the reply gained a second list, 100 -> 120 when it
        # gained is_rumor. Cheap headroom: a truncated reply is unparseable
        # JSON, which costs the whole story's tags.
        max_tokens=120,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": _PROMPT.format(
                    catalog=catalog_text,
                    scopes="    " + "  ".join(scopes),
                    max_n=TEAM_MAX,
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
    teams, dropped = _pick(
        data.get("teams"), team_codes, TEAM_MAX, aliases=aliases or _TEAM_ALIASES
    )
    if not cats and not teams:
        return None
    return Tags(cats, teams, dropped, _rumor(data.get("is_rumor")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=CATEGORY_BATCH_LIMIT)
    parser.add_argument(
        "--retag",
        action="store_true",
        help=(
            "Re-tag stories that are already tagged. For after a prompt or "
            "input change: the normal eligibility rules only re-queue a story "
            "that grew, so improvements never reach the existing corpus."
        ),
    )
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
        team_codes, scopes = load_teams(session)
        if not team_codes:
            print("no teams seeded; run migrations first")
            return 0
        aliases = team_aliases(session)

        pending = stories_needing_categories(session, args.limit, args.retag)
        verb = "will be re-tagged" if args.retag else "need categories"
        print(f"{len(pending)} stories {verb}")

        tagged = skipped = 0
        # Union across the run, not per story: a code the curated list is
        # missing shows up on every story about that team, and one line
        # at the end is what makes the gap actionable.
        unknown: set[str] = set()
        for story_id, title in pending:
            body = build_input(session, story_id, title)
            try:
                tags = classify(client, catalog, team_codes, scopes, body, aliases)
            except RateLimitError:
                # Stop the run, not just this story. The next one resumes
                # exactly here because nothing below got a row.
                print("rate limited -- stopping this run")
                break

            if tags is None:
                # An empty result is a real answer: the story fits nothing.
                # Leaving it untagged is how we find out whether these eight
                # are the right eight -- but it has to be RECORDED, or the
                # story returns to the head of the queue on every future run.
                skipped += 1
                print(f"  no category: {title[:56]}")
                if not args.dry_run:
                    session.execute(
                        text("""
                            update stories
                               set category_attempts = category_attempts + 1,
                                   categorized_outlet_count = (
                                       select count(distinct a.outlet_id)
                                         from story_members sm
                                         join articles a on a.id = sm.article_id
                                        where sm.story_id = :sid)
                             where id = :sid
                        """),
                        {"sid": story_id},
                    )
                    session.commit()
                time.sleep(CATEGORY_PACE_SECONDS)
                continue

            unknown.update(tags.dropped)
            rumor_mark = " [rumor]" if tags.is_rumor else ""
            shown = (
                f"{','.join(tags.categories)} @ "
                f"{','.join(tags.teams) or '-'}{rumor_mark}"
            )
            if args.dry_run:
                # Counted here too, or the summary reads "would tag 0" after
                # printing a screen of tags it would have written.
                tagged += 1
                print(f"  {shown:<40} {title[:44]}")
            else:
                # Delete first: this story may already carry tags from before
                # it grew, and ON CONFLICT DO NOTHING would preserve exactly
                # the stale rows we came back to replace.
                session.execute(
                    text("delete from story_categories where story_id = :sid"),
                    {"sid": story_id},
                )
                session.execute(
                    text("delete from story_teams where story_id = :sid"),
                    {"sid": story_id},
                )
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
                for rank, code in enumerate(tags.teams):
                    session.execute(
                        text("""
                            insert into story_teams
                                (story_id, team_code, rank, relevance)
                            values (:sid, :code, :rank, :relevance)
                            on conflict (story_id, team_code) do nothing
                        """),
                        {
                            "sid": story_id,
                            "code": code,
                            "rank": rank,
                            # Derived from the order the model returned rather
                            # than asked of it as a number -- models score
                            # their own confidence badly, and rank is free.
                            # A section sorts its stories by this.
                            "relevance": 1.0 / (rank + 1),
                        },
                    )
                # Records that this story WAS tagged and at what size, which
                # is what stories_needing_categories reads to decide whether
                # the tags have gone stale. attempts resets: the story is no
                # longer one the model cannot handle.
                session.execute(
                    text("""
                        update stories
                           set categorized_at = now(),
                               category_attempts = 0,
                               is_rumor = :is_rumor,
                               categorized_outlet_count = (
                                   select count(distinct a.outlet_id)
                                     from story_members sm
                                     join articles a on a.id = sm.article_id
                                    where sm.story_id = :sid)
                         where id = :sid
                    """),
                    {"sid": story_id, "is_rumor": tags.is_rumor},
                )
                # One commit for the lot, so a story is never left half-tagged
                # or tagged-but-unrecorded.
                session.commit()
                tagged += 1

            time.sleep(CATEGORY_PACE_SECONDS)

        verb = "would tag" if args.dry_run else "tagged"
        print(f"\n{verb} {tagged}, no category {skipped}")
        if unknown:
            print(
                f"rejected {len(unknown)} unknown team code(s): "
                f"{', '.join(sorted(unknown))}\n"
                "  Real ones are gaps in the curated list -- add with an "
                "INSERT into teams, no migration needed."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
