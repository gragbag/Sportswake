# Task brief: fix clustering (98% singleton rate)

Follow the working rules in CLAUDE.md. **Instruct me, don't write code.** Tell me what to change and where, explain the reasoning, and let me type it. Reading files and running read-only commands is fine without asking.

## Symptom

`scripts/cluster_report.py` reports roughly **3,900 singleton stories out of 4,100 articles** — a ~98% singleton rate across ~47 general-news outlets. Only about 200 articles are in multi-article stories. Major events covered by a dozen outlets are not grouping at all.

A healthy singleton rate for this corpus is somewhere in the 55–75% range. News is power-law distributed and most stories genuinely are singletons, but 98% means the accept path is rejecting true matches.

## Do not do these things

- Do not change more than one variable at a time and then judge by eye.
- Do not tune thresholds before there is a labeled set to tune against.
- Do not add the entity gate yet. It is a precision fix; the current problem is recall.
- Do not touch `worker/ingest.py` or `worker/embed.py`. Ingestion and embedding are working.

## Suspected root cause

`SIMILARITY_THRESHOLD` (0.75) is used for two different jobs:

1. In `candidate_stories()` as the candidate floor: raw cosine ≥ 0.75.
2. In `assign()` as the accept bar, but tested against `cosine * time_factor(gap)`.

Because the decay is multiplicative and ≤ 1, the effective requirement is `cosine × decay ≥ 0.75`, which makes the accept bar age-dependent:

| raw cosine | max gap that still passes (sigma=72h) |
|---|---|
| 1.00 | 54.6 h |
| 0.90 | 43.5 h |
| 0.85 | 36.0 h |
| 0.80 | 25.9 h |
| 0.76 | 11.7 h |

So `CANDIDATE_WINDOW_HOURS = 72` is decorative — the real window is 12–55 hours depending on similarity. Tuning sigma silently moves the accept bar, so sigma and threshold cannot be tuned independently.

Separately, 0.75 raw cosine is likely above where true same-story pairs actually sit for `all-MiniLM-L6-v2` on headline+lede text. That needs to be measured, not assumed.

## Work, in this order

### 1. Measure the actual similarity distribution — before changing anything

I need to know where true matches live before picking a threshold.

Build a labeled pair set: sample article pairs from the corpus, stratified so a good share are plausible near-matches rather than random pairs (random pairs are trivially negative and will flatter any threshold). Target ~200 pairs. Store as `eval/pairs.csv` in the repo. I will hand-label them.

Then write `scripts/eval_clustering.py` that reports precision, recall, and F1 at a given threshold, plus a sweep across a range. Also have it print the cosine distribution for labeled-positive pairs versus labeled-negative pairs separately — that histogram tells me where the bar belongs.

Tell me how to sample the pairs so the stratification is sound. This step gates everything after it.

### 2. Decouple the candidate floor from the accept bar

Split `SIMILARITY_THRESHOLD` in `common/config.py` into two constants:

- `CANDIDATE_MIN_COSINE` — loose (~0.55), used only in `candidate_stories()` to generate candidates.
- `ACCEPT_COSINE` — the real bar, tested against **raw cosine**, not the decayed score.

Change `assign()` so `cosine * time_factor(gap)` is used **only to rank** which candidate story wins, and the accept test is `best_cosine >= ACCEPT_COSINE`. Decay decides *which* story; the threshold decides *whether any of them is close enough*.

Confirm the pre-filter comment in `candidate_stories()` is still accurate after this change — the "exact, not an approximation" claim depends on the filter and the accept test using the same constant, and it won't after this.

Then re-run the eval from step 1 and set `ACCEPT_COSINE` from the measured distribution.

### 3. Score against the best member, not only the centroid

Centroid comparison is average-linkage, which rejects articles that are close to one member but far from the cluster mean. That is the drift problem `merge_pass()` was written to clean up afterward.

Change scoring to `max(cosine_to_centroid, max cosine to any member)`. pgvector can compute the per-story max in the same query that finds candidates. Cap to the N most recent members per story if it gets slow.

Measure before and after on the eval set. If this doesn't move recall, revert it — I don't want the complexity for nothing.

### 4. Separate and raise `MERGE_THRESHOLD`

`MERGE_THRESHOLD` and `SIMILARITY_THRESHOLD` are both 0.75. Centroid-to-centroid similarity runs systematically higher than article-to-centroid because averaging strips idiosyncratic variance, so merging at the assignment bar is far more aggressive than it looks.

Raise it (start ~0.88) and tune it as an independent knob. Note that after fixes 2 and 3 there should be less fragmentation to merge, so re-evaluate whether the merge pass is still earning its complexity.

### 5. Make `merge_pass()` not OOM

`vectors @ vectors.T` over every story is O(n²) — 20k stories is a ~1.6 GB float32 matrix, 50k is ~10 GB. Restrict the candidate set to stories active within `RETIRE_AFTER_DAYS`, or pull candidate pairs from pgvector instead of materializing the full matrix.

### 6. Soft merge

`merge_pass()` hard-deletes the absorbed story. Add `merged_into_id` to `stories` and redirect instead, per `Design.md`. Do this before story URLs are shared anywhere — retrofitting after links exist means broken links that cannot be resolved.

## Acceptance

- `eval/pairs.csv` exists with ~200 hand-labeled pairs, and `scripts/eval_clustering.py` reports precision/recall/F1 plus a threshold sweep.
- Singleton rate drops below 75%.
- The largest cluster spans a plausible number of distinct outlets for a major story (10+, not 2).
- The Gaza funeral and el-Sayed primary probes in `cluster_report.py` each resolve to a single story rather than fragments.
- Every threshold in `common/config.py` has a measured justification, not a guessed one.

## Reminder

Each step should be a separate commit with the eval numbers before and after in the message. If step 3 or 4 doesn't improve the measured result, say so and revert it rather than keeping it because it sounds principled.
