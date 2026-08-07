"""Evaluate clustering against the hand-labelled pair set.

    python scripts/eval_clustering.py

Two numbers that measure different things:

  THRESHOLD SWEEP -- how well raw cosine alone separates the labels. This is
  the ceiling for any threshold-based decision and tells you where
  ACCEPT_COSINE should sit.

  END-TO-END -- whether the clusterer as it actually ran (centroids, time
  decay, merge pass) put each labelled pair in the same story. This is the
  number that matters. The sweep only says what was achievable.

Similarity is recomputed from the database rather than read out of the CSV,
so labels survive a re-embed. Labels are model-independent; scores are not.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, text

from common.config import (
    ACCEPT_COSINE,
    MERGE_THRESHOLD,
    TIME_DECAY_SIGMA_HOURS,
)
from common.models import make_engine

PAIRS = Path("eval/pairs.csv")


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def as_vector(raw) -> np.ndarray:
    if isinstance(raw, str):
        return np.fromstring(raw.strip("[]"), sep=",", dtype=np.float32)
    return np.asarray(raw, dtype=np.float32)


def main() -> int:
    labelled = [r for r in csv.DictReader(PAIRS.open()) if r["label"] in ("y", "n")]
    ids = sorted({r["id_a"] for r in labelled} | {r["id_b"] for r in labelled})

    stmt = text("""
        select a.id, a.embedding,
               coalesce(a.published_at, a.first_seen_at) as t,
               sm.story_id, o.name, a.headline
        from articles a
        join outlets o on o.id = a.outlet_id
        left join story_members sm on sm.article_id = a.id
        where a.id in :ids
    """).bindparams(bindparam("ids", expanding=True))

    with make_engine().connect() as conn:
        rows = conn.execute(stmt, {"ids": ids}).all()

    info = {}
    for aid, emb, t, story_id, outlet, headline in rows:
        vector = as_vector(emb)
        info[str(aid)] = {
            "v": vector / np.linalg.norm(vector),
            "t": t,
            "story": story_id,
            "outlet": outlet,
            "headline": headline,
        }

    pairs = []
    for r in labelled:
        a, b = info.get(r["id_a"]), info.get(r["id_b"])
        if a is None or b is None:
            continue  # article no longer in this database
        gap = abs((a["t"] - b["t"]).total_seconds()) / 3600.0
        pairs.append(
            {
                "same": r["label"] == "y",
                "cos": float(a["v"] @ b["v"]),
                "gap": gap,
                "a": a,
                "b": b,
            }
        )

    n_same = sum(p["same"] for p in pairs)
    print(
        f"{len(pairs)} usable pairs -- {n_same} same, {len(pairs) - n_same} different\n"
    )

    # ---- threshold sweep -------------------------------------------------
    sigma = float(TIME_DECAY_SIGMA_HOURS)
    for label, score in (
        ("cosine only", lambda p: p["cos"]),
        (
            f"cosine x time decay (sigma {TIME_DECAY_SIGMA_HOURS}h)",
            lambda p: p["cos"] * math.exp(-(p["gap"] ** 2) / (2 * sigma * sigma)),
        ),
    ):
        print(f"THRESHOLD SWEEP -- {label}")
        print(f"  {'thresh':>7} {'prec':>6} {'recall':>7} {'F1':>6}   TP  FP  FN")
        best = (0.0, 0.0)
        for i in range(20, 39):
            threshold = i / 40
            tp = sum(1 for p in pairs if score(p) >= threshold and p["same"])
            fp = sum(1 for p in pairs if score(p) >= threshold and not p["same"])
            fn = sum(1 for p in pairs if score(p) < threshold and p["same"])
            precision, recall, f1 = prf(tp, fp, fn)
            mark = " <-- current" if abs(threshold - ACCEPT_COSINE) < 1e-9 else ""
            print(
                f"  {threshold:>7.3f} {precision:>6.3f} {recall:>7.3f} "
                f"{f1:>6.3f} {tp:>4} {fp:>3} {fn:>3}{mark}"
            )
            if f1 > best[1]:
                best = (threshold, f1)
        print(f"  best F1 {best[1]:.3f} at threshold {best[0]:.3f}\n")

    # ---- end to end ------------------------------------------------------
    print(
        f"END-TO-END (as clustered: accept {ACCEPT_COSINE}, "
        f"merge {MERGE_THRESHOLD}, sigma {TIME_DECAY_SIGMA_HOURS}h)"
    )
    together = [
        p
        for p in pairs
        if p["a"]["story"] is not None and p["a"]["story"] == p["b"]["story"]
    ]
    tp = sum(1 for p in together if p["same"])
    fp = len(together) - tp
    fn = sum(1 for p in pairs if p["same"]) - tp
    precision, recall, f1 = prf(tp, fp, fn)
    print(f"  precision {precision:.3f}   recall {recall:.3f}   F1 {f1:.3f}")
    print(f"  TP {tp}  FP {fp}  FN {fn}\n")

    missed = sorted(
        (p for p in pairs if p["same"] and p not in together),
        key=lambda p: -p["cos"],
    )
    print(f"  MISSED -- labelled same, clusterer split them ({len(missed)}):")
    for p in missed[:10]:
        print(
            f"    cos {p['cos']:.3f} {p['gap']:>5.1f}h  "
            f"{p['a']['headline'][:40]} || {p['b']['headline'][:40]}"
        )

    wrong = [p for p in together if not p["same"]]
    print(f"\n  WRONGLY MERGED -- labelled different, clusterer joined ({len(wrong)}):")
    for p in wrong:
        print(
            f"    cos {p['cos']:.3f} {p['gap']:>5.1f}h  "
            f"{p['a']['headline'][:40]} || {p['b']['headline'][:40]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
