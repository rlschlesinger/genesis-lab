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

## Principles

- **The run is the replicate.** Organisms within one population share a history and are not independent samples. Statistics compare runs, not organisms.
- **Paired seeds.** When comparing conditions, use the same set of seeds for each. Because subsystems use independent RNG streams (see decision-log D-006), this reduces noise from differing initial layouts.
- **Report variation.** Always show spread across replicates (for example, median and interquartile range, or every run plotted), not only a mean.
- **Report failures.** Runs that went extinct or crashed are results; they are not discarded silently.
- **Observation vs inference.** "Seekers had higher mean lifespan in 9 of 10 paired runs" is an observation. "Seeking causes longer life" is an inference that needs the controlled design above.
- **No fabricated results.** Numbers in docs come from recorded runs, with their run IDs.
