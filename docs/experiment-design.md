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

## Working hypotheses (from observation, not yet tested)

- **H1 · Energy-limited carrying capacity.** When food is below its cap, the long-run population ≈ `regrowth_per_tick × energy_value ÷ cost per organism per tick`. Derived *after* observing ~112–116 for both controllers with defaults (seed 42), so it needs an independent test: vary `regrowth_per_tick` across seeds and check whether population scales as predicted.
- **H2 · Controllers differ in speed and food left over, not in carrying capacity**, under default settings. Metrics that would show the difference: ticks to reach 90% of capacity, standing food stock, mean lifespan.

## Principles

- **The run is the replicate.** Organisms within one population share a history and are not independent samples. Statistics compare runs, not organisms.
- **Paired seeds.** When comparing conditions, use the same set of seeds for each. Because subsystems use independent RNG streams (see decision-log D-006), this reduces noise from differing initial layouts.
- **Report variation.** Always show spread across replicates (for example, median and interquartile range, or every run plotted), not only a mean.
- **Report failures.** Runs that went extinct or crashed are results; they are not discarded silently.
- **Observation vs inference.** "Seekers had higher mean lifespan in 9 of 10 paired runs" is an observation. "Seeking causes longer life" is an inference that needs the controlled design above.
- **No fabricated results.** Numbers in docs come from recorded runs, with their run IDs.
