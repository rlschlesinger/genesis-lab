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

### Run

Commit `d71ceb1` (clean; all 60 runs `git_dirty: false`). 60 runs, all completed (53 s on this Mac's 14 cores); every run counted (at least 30 alive at the end), so all 20 worlds enter every comparison. Analysis: `uv run python experiments/e009_specialisation.py --analyse-only`, which reproduces every number below exactly.

### Survivors' diets at tick 20,000 (20 worlds per condition)

Mean (sd across worlds):

| Condition | Survivors | Diet spread (sd) | Specialisation, mean \|d − 0.5\| | Below 0.2 (eat A) | Above 0.8 (eat B) | Meals of the favoured kind |
|---|---|---|---|---|---|---|
| **tradeoff** | 159 (16) | **0.225 (0.203)** | **0.459 (0.013)** | 0.50 (0.39) | 0.50 (0.38) | 0.66 (0.05) |
| neutral | 88 (6) | 0.092 (0.045) | 0.113 (0.056) | 0.02 (0.08) | 0.03 (0.12) | 0.50 (0.02) |
| linear | 170 (9) | 0.100 (0.039) | 0.092 (0.032) | 0.01 (0.04) | 0.01 (0.02) | 0.52 (0.02) |

- **H19 (primary): SUPPORTED.** Tradeoff − neutral diet spread = **+0.133**, 95% CI [+0.043, +0.225] (**+144%** of neutral); one-sided p = 0.007. But higher in only **10 of 20** worlds: see H20 and H22.
- **H20 (counts): splits happened only with the trade-off.** Split worlds (≥ 10% of survivors below 0.2 *and* ≥ 10% above 0.8): **tradeoff 9 of 20**, neutral 0 of 20, linear 0 of 20.
- **H21 (estimate): the shape matters.** Tradeoff − linear diet spread = **+0.125**, 95% CI [+0.034, +0.219] (+124%), two-sided p = 0.020. A straight-line trade-off produced no more specialisation than none at all (0.092 vs 0.113).
- **H22 (secondary): SUPPORTED, in every world.** Tradeoff − neutral specialisation = **+0.347**, 95% CI [+0.320, +0.370]; higher in **20 of 20** worlds; one-sided p = 0.00002.

### Interpretation

With a trade-off that makes generalists worse at both foods (k = 2), **specialists emerged in every one of 20 worlds**: by the end, almost no survivor was a generalist (mean distance from 0.5: 0.46 of a possible 0.5). In **9 worlds the population split** into two specialist groups that coexisted to the end; in the other 11, one group took over the whole population. That is why the primary measure, spread, is higher in only half the worlds: a split world has a very large spread (two groups far apart), a taken-over world a very small one (everyone at one end), smaller even than the neutral control's drift. The two outcomes are different answers to "do specialists emerge": yes, always; and they coexist about half the time.

A straight-line trade-off (k = 1), where a generalist is exactly as good on average as a specialist, produced nothing: diets stayed near 0.5, as in the neutral control. What drives specialisation here is the trade-off's *curvature*, the generalist's disadvantage, not the mere existence of two foods.

Drift can't explain this: the neutral control's populations were half the size (88 vs 159), so drifted more, and still stayed generalist.

What this does **not** show: that specialisation would evolve if organisms had to *learn* or *evolve* which food to prefer (here the choice follows the gene by design), or that the groups are species: reproduction is asexual, so there is no interbreeding to stop, and the groups differ in one gene only.

### Exploratory (post hoc, not tested; `experiments/e009_exploratory.py`)

- **Endings of the 20 tradeoff worlds:** 9 split, 6 all on A, 5 all on B, none in between. Which side won in the one-sided worlds looks like chance (6 vs 5; the foods are symmetric).
- **The splits look stable.** In 8 of the 9 split worlds, both ends held at least 10% of the population in every recorded tick of the last 5,000; in the ninth (seed 10000), in 52% of them, so that split may have formed late or may not last.
- **Specialisation takes about half the run.** The first recorded tick at which more than half the population were specialists: median 9,910, range 4,710–14,720. A shorter experiment would have missed it, and some one-sided worlds may yet split (or splits collapse) beyond 20,000 ticks.
- **Candidate question for a new experiment:** what decides split versus takeover? Plausibly how early and how evenly the first specialists of each kind appear (once one kind dominates, the rare other specialists start from too few to grow). Untested.
