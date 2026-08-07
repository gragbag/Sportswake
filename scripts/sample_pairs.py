"""Sample article pairs for hand labelling.

    python scripts/sample_pairs.py            # writes eval/pairs.csv

Stratified by cosine similarity, weighted toward the decision boundary.
Random pairs are trivially negative and would inflate every score, so most
of the budget goes to 0.65-0.85 where the real disagreements live.

Only pairs within the candidate window are sampled -- pairs further apart in
time can never be clustered together, so labelling them teaches nothing.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from common.config import CANDIDATE_WINDOW_HOURS
from common.models import make_engine

OUT = Path("eval/pairs.csv")
SEED = 20260806

# (low, high, how many) -- the budget is deliberately lopsided
BANDS = [
    (0.85, 1.01, 15),  # near-duplicates and wire copy
    (0.75, 0.85, 35),  # upper boundary
    (0.65, 0.75, 50),  # lower boundary -- most disagreements live here
    (0.55, 0.65, 30),  # mostly different, some surprises
    (0.30, 0.55, 20),  # sanity check: these should all be "no"
]


def main() -> int:
    with make_engine().connect() as conn:
        rows = conn.execute(
            text("""
            select a.id, o.name, a.headline, a.embedding,
                   coalesce(a.published_at, a.first_seen_at) as t
            from articles a join outlets o on o.id = a.outlet_id
            where a.embedding is not null
            order by a.id
        """)
        ).all()

    print(f"{len(rows)} embedded articles")
    vectors = np.stack(
        [np.fromstring(str(r[3]).strip("[]"), sep=",", dtype=np.float32) for r in rows]
    )
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    times = np.array([r[4].timestamp() for r in rows], dtype=np.float64)

    rng = np.random.default_rng(SEED)
    seen: set[tuple[int, int]] = set()
    picked: list[tuple[float, float, int, int]] = []

    for low, high, want in BANDS:
        found, attempts = 0, 0
        while found < want and attempts < 400_000:
            attempts += 1
            i, j = rng.integers(0, len(rows), size=2)
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            gap = abs(times[i] - times[j]) / 3600.0
            if gap > CANDIDATE_WINDOW_HOURS:
                continue
            sim = float(vectors[i] @ vectors[j])
            if not (low <= sim < high):
                continue
            seen.add(key)
            picked.append((sim, gap, int(i), int(j)))
            found += 1
        print(f"  {low:.2f}-{high:.2f}: {found}/{want}")

    picked.sort(reverse=True)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "pair_id",
                "label",
                "cosine",
                "hours_apart",
                "outlet_a",
                "headline_a",
                "outlet_b",
                "headline_b",
                "id_a",
                "id_b",
            ]
        )
        for n, (sim, gap, i, j) in enumerate(picked, start=1):
            w.writerow(
                [
                    n,
                    "",
                    f"{sim:.4f}",
                    f"{gap:.1f}",
                    rows[i][1],
                    rows[i][2],
                    rows[j][1],
                    rows[j][2],
                    rows[i][0],
                    rows[j][0],
                ]
            )
    print(f"\nwrote {len(picked)} pairs to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
