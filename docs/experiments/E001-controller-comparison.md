# E001 · Nearest-food seeker vs random walk

**Status:** defined 2026-10-18, before any E001 run. Results are appended below the line, without editing the definition.

## Design

| | |
|---|---|
| **Research question** | Does steering toward sensed food change population outcomes compared with wandering, under the default ecology? |
| **Independent variable** | `organisms.controller`: `random_walk` (control) vs `nearest_food_seeker` |
| **Held constant** | Everything else in `configs/default.yaml` (5000 ticks, food regrowth 2.0/tick, cap 500 organisms) |
| **Replicates** | 10 per condition |
| **Seed strategy** | Paired: seeds 0–9 for both conditions. Each seed gives both controllers the same founders and initial food (tested in `test_controller_choice_does_not_change_the_starting_world`). |
| **Stopping** | 5000 ticks, or extinction (recorded, not discarded) |
| **Unit of analysis** | One run. Organisms within a run are not independent replicates. |

## Dependent variables (per run)

| Metric | Definition |
|---|---|
| `capacity` | Mean population over ticks 2000–4999 (the settled period) |
| `t90` | First tick at which population ≥ 90% of that run's `capacity` |
| `standing_food` | Mean `food_count` over ticks 2000–4999 |
| `lifespan` | Median age at death of organisms that died. Organisms still alive at the end are excluded, which biases this toward shorter lives in both conditions equally (right-censoring). |
| `lineages_end` | Founder lineages alive at the final tick |

## Hypotheses (from the seed-42 observations in 1.7, stated before E001's runs)

- **H2a:** `capacity` differs by less than 10% between controllers (the energy-budget limit of ~114, H1).
- **H2b:** seekers have a lower `t90` (they reach capacity faster).
- **H2c:** seekers have lower `standing_food`.

No prediction for `lifespan` or `lineages_end`; these are exploratory.

## Analysis

For each metric and seed: paired difference = seeker − random walk. Report the median and range of the paired differences, and the number of seeds (out of 10) in which the seeker is higher. No significance tests in Milestone 1 (SciPy arrives in Milestone 3). With 10 pairs, "10 of 10 in the same direction" would happen by chance with probability 2 × 0.5¹⁰ ≈ 0.002 if the controllers did not differ; anything less consistent is reported as-is, without a verdict.

---

## Results

**Run:** 2026-10-18, first at the pre-registration commit (now `0ff8e07`). Re-run at `5c37894` after the history was rewritten to replace the author email; every metric was identical. The recorded run files (all `dirty: false`) point to `5c37894`. Python 3.12.13, NumPy 2.5.4, arm64 macOS. 20 of 20 runs completed 5000 ticks; no extinctions. Raw files: `data/experiments/E001/<controller>-s<seed>/` (not in Git; regenerate with `uv run python experiments/e001_controller_comparison.py`).

### Per-seed values (random walk | seeker)

| seed | capacity | t90 | standing_food | lifespan | lineages_end |
|---:|---|---|---|---|---|
| 0 | 115.8 \| 111.8 | 327 \| 96 | 185.7 \| 21.2 | 316.0 \| 344.5 | 7 \| 7 |
| 1 | 115.0 \| 111.2 | 275 \| 86 | 179.9 \| 21.0 | 326.0 \| 337.0 | 4 \| 7 |
| 2 | 117.6 \| 113.1 | 272 \| 78 | 176.1 \| 19.7 | 337.0 \| 328.0 | 6 \| 7 |
| 3 | 115.0 \| 110.9 | 310 \| 92 | 177.9 \| 21.0 | 313.0 \| 342.0 | 7 \| 11 |
| 4 | 113.3 \| 109.3 | 265 \| 78 | 181.6 \| 21.0 | 317.5 \| 341.0 | 5 \| 6 |
| 5 | 111.0 \| 108.0 | 236 \| 80 | 181.3 \| 20.5 | 321.0 \| 329.0 | 4 \| 7 |
| 6 | 116.0 \| 111.2 | 348 \| 77 | 181.7 \| 21.4 | 333.0 \| 342.0 | 6 \| 7 |
| 7 | 113.3 \| 109.0 | 279 \| 84 | 177.4 \| 21.3 | 310.0 \| 325.5 | 6 \| 7 |
| 8 | 116.7 \| 111.7 | 294 \| 86 | 174.7 \| 20.9 | 329.0 \| 325.0 | 6 \| 10 |
| 9 | 117.1 \| 112.6 | 315 \| 92 | 177.3 \| 21.5 | 319.0 \| 320.0 | 5 \| 10 |

### Paired differences (seeker − random walk)

| metric | median | range | seeker higher |
|---|---:|---|---:|
| capacity | −4.2 (−3.7%) | −4.9 to −3.0 (−4.2% to −2.7%) | 0/10 |
| t90 | −201.5 | −271 to −156 | 0/10 |
| standing_food | −157.9 | −164.5 to −153.8 | 0/10 |
| lifespan | +10.0 | −9.0 to +29.0 | 8/10 |
| lineages_end | +2.0 | 0 to +5 | 9/10 (1 tie) |

### Against the pre-registered hypotheses

- **H2a (capacity within 10%): supported.** Differences are −2.7% to −4.2%.
- **H2b (seekers reach capacity faster): supported, 10/10.** Median t90 85 ticks for seekers vs 286.5 for random walkers.
- **H2c (seekers leave less standing food): supported, 10/10.** ≈ 21 vs ≈ 180 items.

### Unexpected and exploratory (not pre-registered; treat as hypotheses)

- **Seekers settle at a slightly *lower* capacity in 10 of 10 pairs.** Small but perfectly consistent. A post-hoc check on the recorded files: living cost per organism-tick (Σ energy_spent ÷ Σ age) is 0.326 for random walkers vs 0.342 for seekers (ranges 0.3251–0.3267 and 0.3417–0.3427). The measured fact is the cost difference. The *likely* reason, not yet measured directly, is that random walkers spend more time pressed against walls, where they move, and pay, less. By H1, capacity ∝ 1/cost predicts seekers ≈ 4.6% lower; observed 3.7%. **Proposed test (E00x):** repeat E001 with wrap-around edges, or with movement cost charged on requested rather than actual distance. The gap should vanish if this explanation is right.
- **Lifespan:** seekers longer in 8/10, with mixed magnitudes. No conclusion.
- **Lineages:** seekers retained more founder lineages in 9/10 (1 tie). One possible reason: faster early growth gives more founders descendants before competition starts. Untested.

### Limits

Single parameter set (defaults). Lifespan is right-censored (organisms alive at tick 4999 excluded). Metrics like t90 depend on the definition of the settled period (2000–4999), fixed in advance.
