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
# >= 2). At 5: 57 stories qualify today vs 304 at 2 -- bounds the backfill
# to ~3 runs, and stops regen churn on tiny stories (a story summarized at
# 2 outlets would re-summarize at 3, 5, 8 as it grows).
SUMMARY_MIN_OUTLETS: int = int(os.environ.get("SUMMARY_MIN_OUTLETS", "5"))
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
# Groq's limits are PER MODEL. 8b-instant has its own 14,400 req/day pool,
# so categorising the whole backlog cannot starve summarization on
# gpt-oss-120b.
CATEGORY_MODEL: str = os.environ.get("CATEGORY_MODEL", "llama-3.1-8b-instant")
# Every story the feed can show, not just summarized ones -- the summary
# floor is 5 outlets, but the feed shows 2, so tying categories to summaries
# would leave most of the feed untagged.
CATEGORY_MIN_OUTLETS: int = int(os.environ.get("CATEGORY_MIN_OUTLETS", "2"))
CATEGORY_BATCH_LIMIT: int = int(os.environ.get("CATEGORY_BATCH_LIMIT", "60"))
# Two, because a story tagged with more than a quarter of a seven-item
# taxonomy stops being discriminated by its tags at all.
CATEGORY_MAX: int = int(os.environ.get("CATEGORY_MAX", "2"))
# 8b-instant allows 30 req/min; 2s keeps a wide margin without dragging out
# a 60-story batch.
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
# synthesis, and Groq's limits are PER MODEL -- 8b-instant has its own
# 14,400 req/day pool, so comment traffic cannot starve summarization on
# gpt-oss-120b.
MODERATION_GROQ_MODEL: str = os.environ.get(
    "MODERATION_GROQ_MODEL", "llama-3.1-8b-instant"
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
