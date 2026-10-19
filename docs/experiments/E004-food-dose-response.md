# E004 · Does the settled population grow in proportion to food?

**Status:** defined 2026-10-19, before any E004 run (Milestone 3, Experiment A). Results will be appended below the line without editing the definition.

## Why this experiment

H1 (Milestone 1) proposed that, with food below its cap, the long-run population ≈ `regrowth_per_tick × energy_value ÷ living cost per organism per tick`. It fit two settings and E001, but it has never been tested as a *dose-response*: change the food supply and check whether the population follows proportionally.

## Design

| | |
|---|---|
| **Base config** | `configs/default.yaml`: Milestone 1 ecosystem, food-seeking controller, **no mutation**. Evolution would let living costs change and blur the test. |
| **Independent variable** | `food.regrowth_per_tick`: 0.5, 1, 2 (default, the reference), 4 |
| **Seeds** | 4000–4009 (10 per level), shared across levels. Never used before. |
| **Duration** | 5,000 ticks |
| **Metric** | Per run: mean population over ticks 3,000–4,999 ("settled population") |
| **Unit of analysis** | The run (40 runs) |
| **Extinction** | Runs extinct before tick 4,999 are reported and excluded from the fit. More than 4 extinct runs at any level makes the experiment inconclusive. |
| **Pilot** | Feasibility only (seeds 9400–9402, food 0.5 and 4, looking only at extinction and peak population): no extinction; peak 244, below the 500 population cap. |

## Hypotheses

- **H8a (primary): the settled population is proportional to food.** Fit `ln(settled population) = α + β · ln(regrowth)` by least squares over the 40 runs. Proportional means **β = 1** (the *elasticity*: doubling food doubles the population).
  - **Smallest effect of interest:** a deviation of 0.1 from β = 1 (doubling food changing the population by under 1.93× or over 2.07×).
  - **Verdict** from β's 95% bootstrap CI (10,000 resamples of runs within each level, `default_rng(4004)`): *supported* if the CI lies within [0.9, 1.1]; *rejected* if it excludes 1 entirely; *inconclusive* otherwise.
- **H8b (secondary, descriptive): how close is H1's formula in absolute terms?** Per run: predicted = regrowth × 20 ÷ c, where c = Σ`energy_spent` ÷ Σ`age` over that run's organisms (measured living cost per organism-tick). Report the median ratio observed ÷ predicted, with a bootstrap CI, per level. Expectation: slightly below 1, because the formula ignores the energy lost as reproduction overhead. No verdict.

## Limits stated in advance

One controller, no evolution, one world size. Food spawning stops at `max_count` (300 items); if a level hits that cap often, proportionality is expected to break there (the formula assumes food is below its cap). Proportionality "within ±10%" is a claim about this range of food (0.5–4), not beyond it.

**Code check (disclosed):** after this definition was written, the analysis script was exercised by smoke runs (throwaway seeds 9100–9101, 300–600 ticks) to check the code works. Their outputs are not evidence, were deleted, and did not change this definition.

---

## Results

### Run

Commit `8ea2000` (clean; all 40 runs `dirty: false`). 40/40 completed 5,000 ticks; no extinctions; no runs excluded. Analysis: `uv run python experiments/e004_food_dose_response.py --analyse-only`. Dashboard: `uv run genesis dashboard E004`.

### Settled population (mean over ticks 3,000–4,999)

| food regrowth | runs | mean | sd | median | range |
|---:|---:|---:|---:|---:|---|
| 0.5 | 10 | 27.70 | 0.98 | 27.59 | 26.41–29.79 |
| 1 | 10 | 55.62 | 0.71 | 55.65 | 54.34–56.44 |
| 2 | 10 | 110.57 | 1.23 | 110.73 | 109.20–113.27 |
| 4 | 10 | 218.03 | 2.59 | 218.46 | 211.72–220.71 |

### Hypotheses

- **H8a: SUPPORTED.** Elasticity β = **0.992**, 95% CI **[0.982, 1.001]**, entirely within [0.9, 1.1]: the settled population is proportional to food within ±10% (in fact within about ±2%) across an 8-fold range.
- **H8b (descriptive):** observed ÷ H1's prediction, median per level: 0.924 [0.900, 0.946] (food 0.5), 0.940 [0.932, 0.952] (1), 0.947 [0.935, 0.950] (2), 0.944 [0.938, 0.951] (4). As expected, slightly below 1: H1's formula leaves out the energy lost as reproduction overhead. Measured living cost per organism-tick rose slightly with food (0.334 → 0.346 EU/tick).

### Interpretation

H1, proposed after Milestone 1's seed-42 run, now has a pre-registered test: **in this ecosystem, with food below its cap, population scales in proportion to the food supply**, and H1's formula predicts the level to within about 6%.

**Exploratory (not tested):** β's point estimate is slightly below 1 and its CI only just reaches 1. A plausible reason is the small rise in living cost with food (more organisms, more full-speed movement): a cost elasticity of about +0.017 would lower β by about that much. A larger experiment would be needed to show whether the deviation is real.
