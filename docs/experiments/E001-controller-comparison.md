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
