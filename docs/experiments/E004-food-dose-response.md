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
