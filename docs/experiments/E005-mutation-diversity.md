# E005 · Does a higher mutation rate maintain more genetic diversity?

**Status:** defined 2026-10-19, before any E005 run (Milestone 3, Experiment B). Results will be appended below the line without editing the definition.

## Why this experiment

In a population with no selection on a gene, two forces act on its variation: **mutation** adds variation; **drift** removes it (lineages die out by chance, and with them their variants). Theory (*mutation–drift balance*) predicts that the variation they settle at increases with the mutation rate. E002 showed drift-only genes keep some variation; this tests whether that amount responds to the mutation rate as theory says.

## Design

| | |
|---|---|
| **Base config** | `configs/evolution.yaml` with **every gene neutral** (inherited and mutating, but without effect: D-025), so no gene is under selection and hitchhiking can't interfere |
| **Independent variable** | `mutation.rate`: 0 (control), 0.02, 0.1 (the default), 0.3; `mutation.size` fixed at 0.05 |
| **Seeds** | 5000–5009 (10 per rate), shared across rates. Never used before. |
| **Duration** | 20,000 ticks |
| **Metric** | Per run: the neutral marker's standard deviation (across the living population), averaged over ticks 19,000–19,999 |
| **Unit of analysis** | The run |
| **Extinction** | As E002: dropped and reported; more than 2 dropped runs at any rate makes the experiment inconclusive |
| **Pilot** | None needed: these settings (drift-only, plentiful food) never went extinct in E002/E003's 40 neutral runs. |

## Hypotheses

- **C5 (check, not a hypothesis):** with rate 0, the marker's sd is exactly 0 in every run (no mutation, identical founders).
- **H9 (primary): marker variation increases with the mutation rate** across 0.02, 0.1 and 0.3 (30 runs). Test: Spearman rank correlation ρ between rate and per-run sd; two-sided permutation p-value from 20,000 shuffles of the rate labels (`default_rng(5005)`).
  - **Supported** if p < 0.05, ρ > 0, *and* the three medians increase in rate order.
  - **Smallest effect of interest:** a difference of 0.02 in median sd between rates 0.02 and 0.3 (about 7% of the 0.289 a uniform spread would give). Verdict from the 95% bootstrap CI of that difference (meaningful / negligible / inconclusive).
- **Exploratory:** the same comparison for the other five (neutral) genes, reported without verdicts.

## Limits stated in advance

One mutation size; a finite horizon (variation may still be rising at tick 20,000 at the lowest rate). Population size also affects drift; here all conditions share the same ecology, so it is held roughly constant.

**Code check (disclosed):** after this definition was written, the analysis script was exercised by smoke runs (throwaway seeds 9100–9101, 300–600 ticks) to check the code works. Their outputs are not evidence, were deleted, and did not change this definition.

---

## Results
