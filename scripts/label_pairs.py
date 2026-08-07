"""Label sampled pairs. Resumable -- stop and restart whenever.

    python scripts/label_pairs.py

  y = same story    n = different    s = skip/unsure    q = save and quit

"Same story" means the same real-world event, not the same topic. Two articles
about different Michigan primaries are 'n'. An announcement and a reaction to
it are 'n'. Wire copy and an original write-up of the same event are 'y'.
"""

from __future__ import annotations

import csv
from pathlib import Path

PATH = Path("eval/pairs.csv")


def main() -> int:
    with PATH.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())

    todo = [r for r in rows if not r["label"]]
    print(f"{len(rows) - len(todo)}/{len(rows)} already labelled\n")

    try:
        for row in todo:
            print(
                f"--- pair {row['pair_id']}   cos {row['cosine']}   {row['hours_apart']}h apart"
            )
            print(f"  A [{row['outlet_a'][:20]:<20}] {row['headline_a'][:88]}")
            print(f"  B [{row['outlet_b'][:20]:<20}] {row['headline_b'][:88]}")
            while True:
                answer = input("  same story? [y/n/s/q] ").strip().lower()
                if answer in ("y", "n", "s", "q"):
                    break
            if answer == "q":
                break
            if answer != "s":
                row["label"] = answer
            print()
    except (KeyboardInterrupt, EOFError):
        print("\ninterrupted")

    with PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    done = sum(1 for r in rows if r["label"])
    print(f"saved -- {done}/{len(rows)} labelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
