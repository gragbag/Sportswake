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
MERGE_THRESHOLD: float = float(os.environ.get("MERGE_THRESHOLD", "0.75"))

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
