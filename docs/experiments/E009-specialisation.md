# E009 · Does a population split into specialists on two foods?

**Status:** defined 2026-10-21, before any E009 run (Milestone 6, chunk 06B, extension A). Results will be appended below the line without editing the definition. Design approved by the user as the [06B proposal](../roadmap/06B-proposal.md).

## Why this experiment

Chunk 06B's extension A: two resource types with different returns; do specialists emerge? Here food comes in two kinds, A and B, and every organism carries a heritable diet gene `d` from 0 to 1 that sets how much of each kind's energy it keeps (D-063). Organisms head for the kind worth more to them per unit of distance (the `diet_seeker` rule). Only the diet evolves; every other expressed gene is frozen.

The question: when a generalist is worse at both foods than a specialist is at one, does the population **split** into two specialist groups, one per food? Or does it stay generalist, or drift to one side?

## Design

| | |
|---|---|
| **Spec** | `experiments/specs/E009.yaml`, conditions `tradeoff`, `neutral`, `linear` |
| **Config** | `configs/diets.yaml` at commit of this definition: `evolution.yaml`'s world and costs, 100 founders, the diet seeker, every expressed gene but the diet frozen, food energy V = 80 (chosen by the tuning pilots), half of new food B, diet founders at 0.5, mutated like genes (rate 0.1, step sd 0.05) |
| **Conditions** | `tradeoff`: a meal of A gives `V(1 − d)²`, of B `Vd²` (k = 2). `neutral`: `resources.diet.neutral: true`, everyone digests as a generalist (`V/4` per meal, of either kind), so the diet gene only drifts. `linear`: k = 1, `V(1 − d)` and `Vd`. |
| **Seeds** | 10000–10019 (20 worlds, each run in all three conditions: 60 runs). Never used before. |
| **Duration** | 20,000 ticks |
| **Recording** | ticks and diet summaries every 10 ticks; genome snapshots every 1,000; every organism's final diet (`diets.csv`) |
| **Counting** | A run counts if it completes with **at least 30 organisms alive**. Paired comparisons use the worlds where both runs count. Failures are reported; seeds are never replaced. |

### Metrics (per run, over the organisms alive at tick 20,000)

- **Primary: the diet's spread,** its population standard deviation. A population that has split into two groups has a large spread; one that stays generalist, or moves together to one side, a small one.
- **Split:** the run is *split* if at least **10%** of survivors have a diet below **0.2** (eat mostly A) **and** at least 10% above **0.8** (eat mostly B).
- **Specialisation:** the mean distance of survivors' diets from 0.5, `mean |d − 0.5|`. High whether the population specialised on one food or split.
- **Descriptive:** survivors; the shares below 0.2 and above 0.8; *realised diet*, the share of survivors' meals that were of the kind their diet favours.

**Unit of analysis:** the world. Organisms within a run are not independent.

## Hypotheses

Differences are paired by world: *condition A minus condition B on the same seed*.

- **H19 (primary): a trade-off spreads the diet.** `tradeoff − neutral` diet spread > 0. One-sided paired sign-flip permutation test (20,000 samples from `default_rng(9019)`), α = 0.05; reported with the mean difference, its 95% bootstrap CI (10,000 resamples, `default_rng(9119)`), and the number of worlds where `tradeoff` is higher.
- **H20 (counts): splits.** The number of split worlds in each condition. Reported, not tested: the 06B proposal's measure of whether two specialist groups coexist.
- **H21 (estimate): does the trade-off's shape matter?** Mean of `tradeoff − linear` diet spread, 95% bootstrap CI (`default_rng(9021)`), two-sided paired permutation p-value (`default_rng(9121)`). No SESOI; an estimate.
- **H22 (secondary): a trade-off makes specialists, split or not.** `tradeoff − neutral` specialisation > 0. One-sided paired permutation test (`default_rng(9022)`), α = 0.05; 95% bootstrap CI (`default_rng(9122)`). **Added after one disclosed run (below):** that run specialised on one food without splitting, which the primary measure (spread) would not register as specialisation. H22 is therefore labelled secondary, and H19 remains the primary test as proposed.
- **Reported, not tested:** runs that didn't count; survivors per condition; shares at each end; realised diet.

No multiple-comparison correction: H19 is the single primary test; H20 and H21 are counts and an estimate; H22 is labelled secondary.

## Disclosed before this definition

- **Tuning pilots** ([pilots/E009-tuning.md](pilots/E009-tuning.md), seeds 90100–90105, never to be reused): checked only survival and population size, never the diet. All 54 pilots survived at V = 60, 80 and 100 in every condition; V = 80 kept (a generalist's meal is 20 EU, as in every earlier world).
- **One full run seen** while testing the report in 6.9 (`configs/diets.yaml`, seed 1, 20,000 ticks, the `tradeoff` condition): **all survivors became A-specialists** (mean diet 0.04, every survivor below 0.2), with no split. Seed 1 is not an E009 seed. It prompted H22; it changed nothing else.
- **A confounder that favours the null:** neutral worlds settle at about half the population of the others (pilots, V = 80: median 90 against 182). A smaller population drifts more, which spreads the diet *more* in `neutral`, so drift works against H19.
- **Code check:** the script was exercised by smoke runs (throwaway seeds 9100–9101, 3,000 ticks, separate folder and lake). Their outputs are not evidence.

## Limitations stated in advance

- **Choice is designed, not evolved.** The diet seeker follows the gene; what evolves is the gene. Whether brains could evolve the preference is left for a later experiment.
- **One-dimensional specialisation.** Only the diet evolves; speed, senses and metabolism are frozen, so no other trait can specialise with it.
- **Symmetric foods.** A and B are equally common and equally rich; asymmetry is not tested.
- **One threshold for "split".** 10% beyond 0.2 and 0.8 is a stated convention; the full distributions are reported so other readings can be checked.
- **A toy world.** "Split" means two diet groups coexisting in this simulation, not speciation.

---

## Results

*(Appended after the runs, in 6.11.)*
