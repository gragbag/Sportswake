import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EMBEDDING_MODEL: str = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBEDDING_DIM: int = int(os.environ.get("EMBEDDING_DIM", "384"))
# Two different jobs, deliberately two constants. They were one, which made the
# accept bar age-dependent: because decay is multiplicative and <= 1, requiring
# cosine * decay >= 0.75 meant a 0.76 pair had to be within 11.7h at sigma 72h.
# CANDIDATE_WINDOW_HOURS was decorative as a result.
CANDIDATE_MIN_COSINE: float = float(os.environ.get("CANDIDATE_MIN_COSINE", "0.55"))
ACCEPT_COSINE: float = float(os.environ.get("ACCEPT_COSINE", "0.65"))
CANDIDATE_WINDOW_HOURS: int = int(os.environ.get("CANDIDATE_WINDOW_HOURS", "72"))
EMBED_BATCH_SIZE: int = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
TIME_DECAY_SIGMA_HOURS: int = int(os.environ.get("TIME_DECAY_SIGMA_HOURS", "72"))
# 0.85, raised from 0.75 at the same time merge_pass stopped multiplying the
# decay into this comparison. It is not a tightening: because the old test was
# cosine * decay >= 0.75, the bar this system has actually enforced was 0.79 at
# a 24h gap and 0.94 at 48h. Raw 0.75 was therefore looser than anything that
# had ever run, and it showed -- at 0.75 a Michigan Senate primary paired with
# a Milwaukee county race (0.751, 10 and 24 outlets), and a Sony headphone
# rumour with a Sony coupons post. 0.85 sits inside the range that was already
# in force, but as a constant instead of a function of age.
MERGE_THRESHOLD: float = float(os.environ.get("MERGE_THRESHOLD", "0.85"))
# Hard ceiling on how far an article may reach across a story's edge. The time
# decay in cluster.py only RANKS candidates -- it cannot veto one -- so without
# a ceiling a 2024 evergreen explainer, re-served into an RSS feed on a 2026
# news cycle, joins a live story on cosine alone and becomes its first_at.
#
# 30, not 4: measured over 9,722 clustered articles, legitimate slow-burn
# coverage reaches a 15d gap (two outlets on the same Spanish village, 16 days
# apart), while the real offenders start at 40d. 30 sits in the empty band
# between them. Erring high is deliberate -- a bad member dents a big story's
# timeline, but rejecting a good one drops a 2-outlet story below the feed's
# outlet floor and off the site entirely.
MAX_MEMBER_GAP_DAYS: int = int(os.environ.get("MAX_MEMBER_GAP_DAYS", "30"))
# The same ceiling for merge_pass, story-to-story rather than article-to-story.
# It replaces a bound that used to be implicit in the time decay and was far
# tighter than anyone intended: requiring cosine * decay >= MERGE_THRESHOLD
# means a pair 72h apart needs cosine 1.24, so merges simply stopped happening
# past ~60h. Measured over 315 candidate pairs at cosine >= 0.75, the median
# sits 151h apart and only 10% fall inside 3 days -- roughly nine tenths of
# real merges were being refused on time. 30 days keeps 97% of them and still
# cuts the tail, which runs out to 416 days and is all recurring events.
MAX_MERGE_GAP_DAYS: int = int(os.environ.get("MAX_MERGE_GAP_DAYS", "30"))

# ---- summaries (milestone 5) -------------------------------------------
# No key = summarization disabled. Everything else keeps working; cards
# fall back to the seed-article title. This is why every summary column is
# nullable and why worker/summarize.py must exit 0 when the key is absent.
GROQ_API_KEY: str | None = os.environ.get("GROQ_API_KEY")
# OpenAI-compatible endpoint. Switching providers (OpenRouter, etc.) is a
# base-URL + key change, not a code change.
SUMMARY_BASE_URL: str = os.environ.get(
    "SUMMARY_BASE_URL", "https://api.groq.com/openai/v1"
)
# Free-tier ceilings are per model and tokens-per-day binds before requests
# do: gpt-oss-120b allows 200K TPD / 8K TPM vs llama-3.3-70b's 100K TPD.
# Groq rotates its lineup, so this WILL need changing eventually.
SUMMARY_MODEL: str = os.environ.get("SUMMARY_MODEL", "openai/gpt-oss-120b")
# Stories per run. At ~2K tokens/story, 25 stories is ~50K tokens -- a
# quarter of the daily budget, leaving room for regens and reruns.
SUMMARY_BATCH_LIMIT: int = int(os.environ.get("SUMMARY_BATCH_LIMIT", "25"))
# Re-summarize only when distinct outlets grew by this factor since the last
# summary. 1.5 means a 10-outlet story regenerates at 15, not at 11.
SUMMARY_REGEN_GROWTH: float = float(os.environ.get("SUMMARY_REGEN_GROWTH", "1.5"))
# Input cap: ONE article per outlet, at most this many outlets. 101 members
# is ~42 near-identical wire rewrites; the model needs the comparison set,
# not the volume.
SUMMARY_MAX_OUTLETS: int = int(os.environ.get("SUMMARY_MAX_OUTLETS", "30"))
# Floor for summarization, NOT for display (the front page keeps showing
# >= 2). Lowered 5 -> 3 once the feed became a browsing surface again: at 5
# most cards showed raw seed headlines, and half of the 2+ corpus sits at
# exactly 2. Three is the balance -- it roughly halves the unsummarized
# feed while still skipping the two-outlet tier, which is mostly wire-copy
# pairs with nothing to compare, and where regen churn is worst (a story
# summarized at 2 re-summarizes at 3, 5, 8 as it grows; from 3 the next
# regen is ~5).
SUMMARY_MIN_OUTLETS: int = int(os.environ.get("SUMMARY_MIN_OUTLETS", "3"))
# Seconds between LLM calls. 8K TPM at ~2K tokens/story caps at ~4
# stories/minute; 20s stays under it without thinking about it.
SUMMARY_PACE_SECONDS: int = int(os.environ.get("SUMMARY_PACE_SECONDS", "20"))


# ---- comments (milestone 8) ---------------------------------------------
# Two windows, deliberately. A daily cap alone lets someone spend all ten in
# ten seconds, which is the shape a flame war takes; the hourly cap stops the
# burst and the daily cap bounds the total.
COMMENT_MAX_PER_HOUR: int = int(os.environ.get("COMMENT_MAX_PER_HOUR", "3"))
COMMENT_MAX_PER_DAY: int = int(os.environ.get("COMMENT_MAX_PER_DAY", "10"))
# Per user per story, NOT per story. A cap on the story silences the 26th
# person for being late; this one targets the actual failure, which is one
# person dominating a thread.
COMMENT_MAX_PER_STORY: int = int(os.environ.get("COMMENT_MAX_PER_STORY", "5"))
# Long enough for a real point, short enough to discourage manifestos. The
# database also has a CHECK at 4000 as a backstop against a client that
# ignores this.
COMMENT_MAX_LENGTH: int = int(os.environ.get("COMMENT_MAX_LENGTH", "2000"))
# Read page size. Bounds the query and the payload without ever closing a
# thread.
COMMENT_PAGE_SIZE: int = int(os.environ.get("COMMENT_PAGE_SIZE", "50"))
# Nesting cap. 0 is top level, so 3 allows a reply, a counter-reply, and one
# more. Unlimited nesting indents into a column two characters wide and
# multiplies the moderation surface without deepening the conversation.
COMMENT_MAX_DEPTH: int = int(os.environ.get("COMMENT_MAX_DEPTH", "3"))


# ---- categories ---------------------------------------------------------
# The small model, deliberately: this is classification, not synthesis, and
# Groq's limits are PER MODEL. gpt-oss-20b has its own request pool, so
# categorising the whole backlog cannot starve summarization on
# gpt-oss-120b. (Was llama-3.1-8b-instant until Groq retired the Llama
# line, 2026-08.)
CATEGORY_MODEL: str = os.environ.get("CATEGORY_MODEL", "openai/gpt-oss-20b")
# Every story the feed can show, not just summarized ones -- the summary
# floor is 5 outlets, but the feed shows 2, so tying categories to summaries
# would leave most of the feed untagged.
CATEGORY_MIN_OUTLETS: int = int(os.environ.get("CATEGORY_MIN_OUTLETS", "2"))
CATEGORY_BATCH_LIMIT: int = int(os.environ.get("CATEGORY_BATCH_LIMIT", "60"))
# Two, because a story tagged with more than a quarter of a seven-item
# taxonomy stops being discriminated by its tags at all.
CATEGORY_MAX: int = int(os.environ.get("CATEGORY_MAX", "2"))
# 2s sits well under the small model's per-minute ceiling without dragging
# out a 60-story batch.
CATEGORY_PACE_SECONDS: float = float(os.environ.get("CATEGORY_PACE_SECONDS", "2"))
# Teams are assigned by the same call as categories -- same evidence, and a
# second request would double the rate-limit cost to answer a question the
# model has already read the input for.
#
# THREE, where categories get two. A trade has two sides by definition, so a
# cap of two leaves no room for the third club that so often routes salary,
# and three-team deals are common enough that truncating one would quietly
# drop a team from its own trade. Categories have no equivalent case.
TEAM_MAX: int = int(os.environ.get("TEAM_MAX", "3"))
# Re-tag once a story has grown this much since it was last tagged. Mirrors
# SUMMARY_REGEN_GROWTH, and matters far more now that merge_pass actually
# merges: a story that absorbs another is describing a different member set
# than the one its tags were derived from.
CATEGORY_REGEN_GROWTH: float = float(os.environ.get("CATEGORY_REGEN_GROWTH", "1.5"))
# Give up after this many attempts that yield nothing usable. Growth still
# reopens the story, so this bounds wasted calls rather than closing the door.
CATEGORY_MAX_ATTEMPTS: int = int(os.environ.get("CATEGORY_MAX_ATTEMPTS", "3"))


# ---- importance ----------------------------------------------------------
# What decides whether a story is worth a brief at all, and how much room it
# earns. Computed arithmetic, never an LLM judgement: a model asked how
# important its own story is will inflate, every time.
#
# The four weights sum to 1.0 and EVERY TERM IS BOUNDED TO 0-1 BEFORE
# WEIGHTING, so the composite needs no rescaling and -- critically -- means a
# score is comparable across time. Rolling min-max normalization was rejected
# for exactly this: its denominator moves whenever a bigger story lands, which
# retroactively rescales old scores and quietly invalidates the trailing
# percentile the major-story override depends on.
IMPORTANCE_W_SOURCES: float = float(os.environ.get("IMPORTANCE_W_SOURCES", "0.35"))
IMPORTANCE_W_RECENCY: float = float(os.environ.get("IMPORTANCE_W_RECENCY", "0.30"))
IMPORTANCE_W_AUTHORITY: float = float(os.environ.get("IMPORTANCE_W_AUTHORITY", "0.20"))
IMPORTANCE_W_GAME: float = float(os.environ.get("IMPORTANCE_W_GAME", "0.15"))
# Outlet count at which the corroboration term saturates. Beyond this, more
# coverage stops being evidence -- the difference between 15 outlets and 25 is
# not the difference between 2 and 12.
IMPORTANCE_SOURCE_SATURATION: int = int(
    os.environ.get("IMPORTANCE_SOURCE_SATURATION", "15")
)
# Its OWN sigma, deliberately not TIME_DECAY_SIGMA_HOURS (72). Reusing the
# clustering constant would couple two unrelated questions: "can a new article
# still join this story" and "has this story stopped being brief-worthy". A
# story stays clusterable far longer than it stays news.
IMPORTANCE_DECAY_SIGMA_HOURS: int = int(
    os.environ.get("IMPORTANCE_DECAY_SIGMA_HOURS", "18")
)
# Eligibility floor for any brief. Absolute, on a scale that is stable across
# time -- unlike MAJOR_STORY_PERCENTILE, which is relative by design. Both
# kinds of gate can coexist only because the underlying score is comparable,
# which is what the bounded-terms rule above buys.
#
# 0.55, set from the measured distribution rather than picked. Over a 271-story
# window the corpus ran min 0.16 / median 0.41 / max 0.85, and the candidate
# cuts were:
#     >= 0.35   172 stories      >= 0.55    25 stories
#     >= 0.45    83 stories      >= 0.60    14 stories
#     >= 0.50    45 stories      >= 0.65     9 stories
#
# 0.35 sat almost exactly on the median, which is not a significance filter --
# it admitted "Former LeBron James teammate reveals why he didn't return to
# Cleveland": ONE outlet, an aggregator at 0.35 authority, qualifying purely
# because it was 16 hours old. Recency is weighted 0.30 and decays slowly
# enough over a day that freshness alone carried a single-source item over the
# line. That is precisely the padding the product is supposed to refuse.
#
# At 0.55 a lone aggregator story cannot qualify at any age (its ceiling is
# 0.46 without a linked game), while a single ESPN report on a real game still
# can. ~25 stories per four days is roughly six a day, which is a league
# section plus a few team sections -- the intended shape.
#
# NOTE this floor is ABSOLUTE while news volume is seasonal. It was tuned in
# August, the quietest month of the calendar; in-season the same cut will admit
# considerably more, which is correct (more real news happens) but means it
# should be re-read against a February corpus before being trusted.
IMPORTANCE_THRESHOLD: float = float(os.environ.get("IMPORTANCE_THRESHOLD", "0.55"))
# How far back a run recomputes. NOT a dirty flag like needs_merge: recency
# decays with the wall clock and no write occurs, so a flag would freeze every
# idle story's score at whatever it was when its last member arrived. Matches
# cluster.py's RETIRE_AFTER_DAYS rather than inventing a new horizon; past it,
# at sigma 18h, the decay term is already numerically negligible.
IMPORTANCE_RECOMPUTE_WINDOW_DAYS: int = int(
    os.environ.get("IMPORTANCE_RECOMPUTE_WINDOW_DAYS", "4")
)


# ---- briefs --------------------------------------------------------------
# Sections are generated PER TEAM, never per user: one league section plus one
# per team with qualifying news, so a slot costs at most 31 generations no
# matter how many people read it. A reader's brief is assembled from those
# rows at read time. Ten thousand Lakers fans consume one generation, and
# following twelve teams consumes none.
#
# A SEPARATE MODEL FROM SUMMARY_MODEL, deliberately, and this must stay true.
# Groq's limits are per model, and summarize.py aborts its ENTIRE run on a
# rate-limit error. If briefs shared gpt-oss-120b, a burst at 08:00 ET could
# exhaust the pool and silently stall that hour's summarization for the rest
# of the day -- with categorize unaffected and nothing in either workflow's
# logs pointing at the cause. Two independently-scheduled workflows must not
# share one budget.
#
# qwen3.6-27b is the largest surviving model OUTSIDE the gpt-oss pools after
# Groq retired the Llama line (2026-08, which took the original
# llama-3.3-70b-versatile). It is a reasoning model that leaks <think>
# blocks into plain completions -- but json_object mode suppresses them and
# returns clean JSON, verified against the live API before this default
# changed. If brief generation ever stops using json_object, re-test that.
BRIEF_MODEL: str = os.environ.get("BRIEF_MODEL", "qwen/qwen3.6-27b")
BRIEF_BASE_URL: str = os.environ.get("BRIEF_BASE_URL", SUMMARY_BASE_URL)
BRIEF_PACE_SECONDS: float = float(os.environ.get("BRIEF_PACE_SECONDS", "3"))

# Targets, not laws. A slow day produces a shorter brief; padding to reach a
# number is the failure this product is trying to avoid.
BRIEF_WORDS_MORNING: int = int(os.environ.get("BRIEF_WORDS_MORNING", "300"))
BRIEF_WORDS_MIDDAY: int = int(os.environ.get("BRIEF_WORDS_MIDDAY", "100"))
BRIEF_WORDS_NIGHT: int = int(os.environ.get("BRIEF_WORDS_NIGHT", "800"))

# Ceilings on the major-story expansion, per slot. A 100-word midday brief is
# allowed to become 600 when a superstar is traded; it is not allowed to
# become 2000.
BRIEF_EXPANSION_MORNING: int = int(os.environ.get("BRIEF_EXPANSION_MORNING", "300"))
BRIEF_EXPANSION_MIDDAY: int = int(os.environ.get("BRIEF_EXPANSION_MIDDAY", "500"))
BRIEF_EXPANSION_NIGHT: int = int(os.environ.get("BRIEF_EXPANSION_NIGHT", "500"))

# Extra words must be EARNED BY EXTRA FACTS, never by elaboration. A section
# on a major story should read denser, not more florid -- so the budget is a
# function of counted facts, and the model never learns why its number is
# what it is.
WORDS_PER_FACT: int = int(os.environ.get("WORDS_PER_FACT", "25"))
WORDS_PER_EXTRA_CLUSTER: int = int(os.environ.get("WORDS_PER_EXTRA_CLUSTER", "40"))
# Facts the base word count already pays for; expansion starts above this.
BASELINE_FACTS_INCLUDED: int = int(os.environ.get("BASELINE_FACTS_INCLUDED", "4"))

# The major-story gate. RELATIVE, never an absolute source count: coverage
# volume swings enormously across the calendar, so eight outlets on one story
# is extraordinary in late August and unremarkable during the Finals. A fixed
# number would fire constantly in May and never in September.
MAJOR_STORY_PERCENTILE: float = float(os.environ.get("MAJOR_STORY_PERCENTILE", "0.97"))
IMPORTANCE_ROLLING_WINDOW_DAYS: int = int(
    os.environ.get("IMPORTANCE_ROLLING_WINDOW_DAYS", "30")
)

BRIEF_MAX_CLUSTERS_PER_SECTION: int = int(
    os.environ.get("BRIEF_MAX_CLUSTERS_PER_SECTION", "12")
)
# Rendered sections per slot, at READ time. Generation is uncapped at 31; this
# is what keeps a brief readable for someone following twelve teams. Lifted
# when a major story is present.
BRIEF_MAX_RENDERED_SECTIONS: int = int(
    os.environ.get("BRIEF_MAX_RENDERED_SECTIONS", "6")
)
# Reject and retry once past this multiple of the budget. Without a hard
# check nothing stops an 800-word budget returning 1,400 words, which makes
# the whole fact-counted budget advisory.
BRIEF_OVERRUN_FACTOR: float = float(os.environ.get("BRIEF_OVERRUN_FACTOR", "1.5"))

# Everything is decided in Eastern because the NBA calendar is. Display is
# anchored to the reader's own clock; generation never is.
BRIEF_TZ: str = os.environ.get("BRIEF_TZ", "America/New_York")
# Which editions actually publish. The full machinery knows three; how many
# run on a given day is an editorial call that tracks news volume -- the
# offseason does not fill three briefs -- so it lives in the environment,
# not in code or cron. due_slots() only offers slots named here; --slot
# --force can still generate a disabled one by hand.
BRIEF_SLOTS_ENABLED: frozenset[str] = frozenset(
    os.environ.get("BRIEF_SLOTS", "morning,midday,night").split(",")
)
MORNING_SLOT_ET_HOUR: int = int(os.environ.get("MORNING_SLOT_ET_HOUR", "8"))
MIDDAY_SLOT_ET_HOUR: int = int(os.environ.get("MIDDAY_SLOT_ET_HOUR", "14"))
# Wait after the last game goes final, so reaction pieces land in the feeds
# before the night brief reads them.
NIGHT_POST_FINAL_WAIT_MINUTES: int = int(
    os.environ.get("NIGHT_POST_FINAL_WAIT_MINUTES", "30")
)
NIGHT_FALLBACK_ET_HOUR: int = int(os.environ.get("NIGHT_FALLBACK_ET_HOUR", "23"))
NIGHT_FALLBACK_ET_MINUTE: int = int(os.environ.get("NIGHT_FALLBACK_ET_MINUTE", "30"))
# Second, independent fallback: 02:00 ET the following day. "All games final"
# has no answer for a game that NEVER reaches final -- a stuck status, a
# suspension, an upstream outage -- and without this a single bad status flag
# means the night brief never fires at all, silently, for that day. The
# product spec names only the no-games fallback; this covers the other hole.
NIGHT_HARD_CEILING_ET_HOUR: int = int(os.environ.get("NIGHT_HARD_CEILING_ET_HOUR", "2"))
# A three-day outage should resume with today's slots, not manufacture a
# backlog of stale dated briefs nobody will read.
BRIEF_MAX_BACKFILL_DAYS: int = int(os.environ.get("BRIEF_MAX_BACKFILL_DAYS", "1"))

# Where the calendar is, as (month, day) -> phase. Read by the generator as
# CONTEXT ONLY -- there is deliberately no branching on phase anywhere, because
# the importance threshold already handles volume: draft night produces a full
# brief and late August produces almost nothing, and both are correct without
# special-casing.
#
# It exists because a model with no sense of the date invents one. Left to
# itself it wrote "The NBA season is underway" in the middle of August, which
# is the kind of confident background detail that is invisible until a reader
# notices the product does not know what month it is.
SEASON_PHASES: tuple[tuple[tuple[int, int], str], ...] = (
    ((1, 1), "regular season"),
    ((4, 16), "the playoffs"),
    ((6, 26), "the draft"),
    ((7, 1), "free agency"),
    ((7, 11), "summer league"),
    ((8, 1), "the off-season dead period, with no games being played"),
    ((10, 1), "preseason"),
    ((10, 15), "regular season"),
)


# ---- scores (BallDontLie) ------------------------------------------------
# The structured layer. Every number a brief quotes comes from here, never
# from article text -- which is the whole defence against a stale or invented
# stat arriving through a headline. No key = games and box scores simply do
# not update; the same "off, not broken" contract GROQ_API_KEY has, because a
# billing lapse must not take the rest of the pipeline down with it.
BALLDONTLIE_API_KEY: str | None = os.environ.get("BALLDONTLIE_API_KEY")
BALLDONTLIE_BASE_URL: str = os.environ.get(
    "BALLDONTLIE_BASE_URL", "https://api.balldontlie.io/v1"
)
BALLDONTLIE_TIMEOUT_SECONDS: float = float(
    os.environ.get("BALLDONTLIE_TIMEOUT_SECONDS", "15")
)
# Per-player stat lines are an ALL-STAR-tier endpoint, which allows 60
# requests per minute. One second between calls sits an order of magnitude
# inside that without thinking about it, and a poll is a handful of requests.
BALLDONTLIE_PACE_SECONDS: float = float(
    os.environ.get("BALLDONTLIE_PACE_SECONDS", "1.0")
)
# How far back each poll re-reads. 2, not 1: a West Coast game tipping at
# 22:30 ET finishes on the NEXT UTC day, and a provider may correct a score
# after the fact. Re-reading is cheap and the upsert is idempotent.
SCORES_LOOKBACK_DAYS: int = int(os.environ.get("SCORES_LOOKBACK_DAYS", "2"))
# Tomorrow's slate, so the morning brief can say what is coming.
SCORES_LOOKAHEAD_DAYS: int = int(os.environ.get("SCORES_LOOKAHEAD_DAYS", "1"))
# Games per run to pull box scores for. Bounds a first run against a long
# backlog; steady state is a dozen games a night.
SCORES_BOX_BATCH_LIMIT: int = int(os.environ.get("SCORES_BOX_BATCH_LIMIT", "30"))


# ---- profiles -----------------------------------------------------------
# Renaming frees the old handle for anyone else to take, which makes rapid
# renames an identity-swap tool. A cooldown makes that impractical without
# forbidding renames outright, the way Reddit and Mastodon do.
USERNAME_COOLDOWN_DAYS: int = int(os.environ.get("USERNAME_COOLDOWN_DAYS", "30"))
# Names the product needs to keep, so nobody can imply they speak for it.
USERNAME_RESERVED: frozenset[str] = frozenset(
    {
        "admin",
        "administrator",
        "moderator",
        "mod",
        "staff",
        "support",
        "presswake",
        "official",
        "help",
        "root",
        "system",
        "null",
        "undefined",
        "me",
        "you",
        "anonymous",
        "deleted",
    }
)


# ---- comment moderation -------------------------------------------------
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")
# "openai" | "groq". Both sit behind one interface in app/moderation.py, so
# losing an account is an env change rather than a rewrite -- the same reason
# SUMMARY_BASE_URL exists.
MODERATION_PROVIDER: str = os.environ.get("MODERATION_PROVIDER", "openai")
MODERATION_OPENAI_URL: str = "https://api.openai.com/v1/moderations"
MODERATION_OPENAI_MODEL: str = "omni-moderation-latest"
# Groq fallback. Deliberately the small model: this is classification, not
# synthesis, and Groq's limits are PER MODEL -- gpt-oss-20b's pool is
# separate from gpt-oss-120b, so comment traffic cannot starve
# summarization. It shares categorize's pool, exactly as the two shared
# 8b-instant before the Llama retirement.
MODERATION_GROQ_MODEL: str = os.environ.get(
    "MODERATION_GROQ_MODEL", "openai/gpt-oss-20b"
)
# Short: this call sits in the comment POST path. A slow classifier should
# park the comment for retry, not make the user wait.
MODERATION_TIMEOUT_SECONDS: float = float(
    os.environ.get("MODERATION_TIMEOUT_SECONDS", "5")
)

# Per-category thresholds, not one threshold on the maximum score.
#
# Measured on sample comments: "Stevens is a corrupt sellout... anyone who
# voted for her is an idiot" scores harassment 0.89, while "these people are
# animals and don't belong in our country" scores harassment 0.88 -- the max
# cannot tell them apart. What separates them is hate: 0.33 vs 0.57.
#
# So harassment is deliberately loose (robust political argument lives
# there, and a politics site that deletes it has no comment section worth
# having) while hate and violence are strict. The two at 0.2 are categories
# where a false negative is catastrophic and a false positive costs nothing.
MODERATION_THRESHOLDS: dict[str, float] = {
    # False negative catastrophic, false positive costs nothing.
    "sexual/minors": 0.2,
    "self-harm/instructions": 0.2,
    # Clean discriminators. Measured near zero on every acceptable sample
    # and high on genuine abuse -- "kill yourself, loser" scores
    # harassment/threatening 0.76 and self-harm/intent 0.94, while harsh
    # political comment scores 0.001 and 0.0002 on the same two.
    "harassment/threatening": 0.5,
    "hate/threatening": 0.5,
    "illicit/violent": 0.5,
    "self-harm/intent": 0.5,
    "violence": 0.5,
    # Separates dehumanising language (0.57) from political anger (0.33).
    "hate": 0.5,
    # Deliberately near-inert. Measured: mild rudeness 0.81, criticism of a
    # writer 0.84, harsh political comment 0.89, real abuse 0.96. There is
    # no threshold that removes the last without removing the first three,
    # so this sits above ordinary anger and the real work is done by the
    # categories above. A politics site that deletes "anyone who voted for
    # her is an idiot" has no comment section worth having.
    "harassment": 0.95,
}


# ---- auth (milestone 6) -------------------------------------------------
def _project_ref() -> str | None:
    """Pull the Supabase project ref out of DATABASE_URL.

    Pooler connection strings use `postgres.<project-ref>` as the username,
    so the ref is already in the one secret we always have. Returns None for
    the local Docker URL (plain `postgres`, no dot), which is what makes
    SUPABASE_URL None and turns auth off rather than crashing.
    """
    url = os.environ.get("DATABASE_URL", "")
    user = urlsplit(url).username or ""
    ref = user.split(".", 1)[1] if "." in user else ""
    return ref or None


_REF = _project_ref()
# Explicit env var wins; derivation is the convenience path.
SUPABASE_URL: str | None = os.environ.get("SUPABASE_URL") or (
    f"https://{_REF}.supabase.co" if _REF else None
)
# Public keys only -- Supabase signs with ES256 and publishes the verifying
# half here, so the API holds no auth secret at all.
SUPABASE_JWKS_URL: str | None = (
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else None
)
# Supabase stamps every logged-in access token with these two claims.
SUPABASE_JWT_AUDIENCE: str = "authenticated"
SUPABASE_JWT_ISSUER: str | None = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None
