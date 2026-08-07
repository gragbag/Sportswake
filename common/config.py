import os
from pathlib import Path

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
