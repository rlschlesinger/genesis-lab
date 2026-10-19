# Experiment design

How formal experiments in Genesis Lab are specified and analyzed. This document grows with Milestone 3; the rules below already apply.

## Every formal experiment declares, before running

- Research question
- Hypothesis (stated so that a result could contradict it)
- Independent variable(s) and the levels tested
- Dependent variable(s), with exact metric definitions
- Control condition
- Number of independent replicates
- Seed strategy (for example: seeds 0–29, shared across conditions)
- Simulation duration and stopping conditions (including extinction)
- Analysis method

## Working hypotheses

Formal experiments live in [experiments/](experiments/), one file per experiment, defined before running.

- **H1 · Energy-limited carrying capacity.** When food is below its cap, the long-run population ≈ `regrowth_per_tick × energy_value ÷ cost per organism per tick`. Derived *after* observing ~112–116 for both controllers with defaults (seed 42), so it needs an independent test: vary `regrowth_per_tick` across seeds and check whether population scales as predicted. E001's capacities (108–118) fit it, given that cost per tick is 0.326–0.342 rather than 0.35. Still untested as a dose-response.
- **H2 · Controllers differ in speed and food left over, not in carrying capacity**, under default settings. **Tested in [E001](experiments/E001-controller-comparison.md): supported** (capacity within 2.7–4.2%; seekers faster and leave less food in 10/10 paired seeds). E001 also found a small, consistent capacity *deficit* for seekers, with a proposed wall-cost explanation that is not yet tested.

- **H3 · Neutral drift.** With identical organisms, founder lineages are lost at random. Observed (seed 42, defaults): 30 → 22 at tick 1000 → 8 at tick 4999. Needs replicates to establish the typical rate and spread; this becomes the null model for Milestone 2's selection experiments.

## Statistical tests (genesis.analytics.significance)

- **Paired designs** (shared seeds): `paired_permutation_test` on per-seed differences (uses sizes); `sign_test` (direction only, robust to outliers). Exact for ≤ 16 pairs; otherwise sampled with a seeded generator and the +1 correction.
- **Independent groups:** `permutation_test`.
- **Several hypotheses in one experiment:** report Holm-adjusted p-values.
- **Resolution limit:** with n pairs the smallest possible two-sided p is 2 / 2ⁿ (0.002 for 10, 0.000004 for 20). Choose n before running.
- **Significant ≠ large:** always report the effect size (mean or median difference, and range) beside the p-value. A hypothesis about size ("within 10%") isn't tested by "is there a difference?".
- **Drift isn't always centred:** under drift with reflection, a gene's mean tends toward the middle of its range. Predictions must state the drift expectation for each gene (e.g. metabolic_rate starts at 0.2, below its midpoint 0.26, so drift alone would push it *up*).

## Principles

- **The run is the replicate.** Organisms within one population share a history and are not independent samples. Statistics compare runs, not organisms.
- **Paired seeds.** When comparing conditions, use the same set of seeds for each. Because subsystems use independent RNG streams (see decision-log D-006), this reduces noise from differing initial layouts.
- **Report variation.** Always show spread across replicates (for example, median and interquartile range, or every run plotted), not only a mean.
- **Report failures.** Runs that went extinct or crashed are results; they are not discarded silently.
- **Observation vs inference.** "Seekers had higher mean lifespan in 9 of 10 paired runs" is an observation. "Seeking causes longer life" is an inference that needs the controlled design above.
- **Fresh seeds for confirmatory tests.** Seeds used for exploring or previewing (seed 42 in increments 2.3–2.4) are not reused to test hypotheses those previews suggested. Each pre-registered experiment names its own seed range.
- **No fabricated results.** Numbers in docs come from recorded runs, with their run IDs.
