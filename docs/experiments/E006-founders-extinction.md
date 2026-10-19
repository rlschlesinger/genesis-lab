# E006 · Do smaller founding populations go extinct more often?

**Status:** defined 2026-10-19, before any E006 run (Milestone 3, Experiment C). Results will be appended below the line without editing the definition.

## Why this experiment

A small group can die out by bad luck alone: a few failed searches for food, and nobody is left to reproduce (*demographic stochasticity*). A larger group spreads that risk. The prediction: **the fewer the founders, the higher the chance of extinction**. The outcome is yes/no per run, so this experiment uses proportions, Wilson intervals and a trend test instead of means.

## Design

| | |
|---|---|
| **Base config** | `configs/default.yaml` (no mutation) with a harsh environment: **no starting food** (`food.initial_count: 0`) and **food regrowth 0.1 items per tick** |
| **Independent variable** | `organisms.initial_count` (founders): 2, 5, 10, 20, 40 |
| **Seeds** | 6000–6049 (**50 per level**), shared across levels. Never used before. |
| **Duration** | 3,000 ticks; runs stop early at extinction |
| **Outcome** | Per run: extinct before tick 3,000 (`stop_reason = 'extinction'`), yes/no |
| **Unit of analysis** | The run (250 runs) |

### Pilots (disclosed in full)

Extinction is the outcome itself, so calibrating where it happens means looking at it. Two pilots, on seeds never used in the experiment, recorded only extinction counts (10 runs per cell, 3,000 ticks):

| starting food | regrowth | 2 founders | 10 founders | 40 founders |
|---|---|---|---|---|
| 150 (default) | 0.2 / 0.3 / 0.5 | 0 / 0 / 0 | 1 / 0 / 0 | 0 / 0 / 0 |
| 0 | 0.1 | 6 | 7 | 4 |
| 0 | 0.2 | 0 | 1 | 0 |
| 10 | 0.1 | 4 | 6 | 6 |
| 10 | 0.2 | 0 | 0 | 0 |

With default starting food, extinction almost never happens; with none and regrowth 0.1, it happens in 40–70% of runs (away from 0% and 100%, where differences can't show). That setting was chosen. **The pilots showed no clear founder trend** (10 runs per cell is far too few), so the hypothesis below comes from theory, not from the pilots.

## Hypotheses

- **H10 (primary): extinction probability decreases as founders increase.** Test: the correlation between log₂(founders) and extinction (1 = extinct) over the 250 runs, a permutation version of the Cochran–Armitage trend test; two-sided p from 20,000 shuffles of the founder labels (`default_rng(6006)`). **Supported** if p < 0.05 and the correlation is negative.
- **Practical significance:** the difference in extinction probability between 2 and 40 founders, with a 95% bootstrap CI (10,000 resamples of runs within each level, `default_rng(6007)`). **Smallest effect of interest:** 0.15 (15 percentage points). Verdict: meaningful / negligible / inconclusive.
- **Reported per level:** extinction proportion with its 95% Wilson interval.
- **Exploratory:** median tick of extinction among runs that went extinct, per level.

## A risk stated in advance

At regrowth 0.1 the world supports only about 6 organisms (H1: 0.1 × 20 ÷ 0.35 ≈ 5.7). Long-run extinction may therefore be driven by that low capacity whatever the starting number, and founders may matter only for *early* extinction. A null or weak result for H10 would then be a genuine finding about this regime, not a failed experiment; the exploratory timing analysis would help interpret it.

**Code check (disclosed):** after this definition was written, the analysis script was exercised by smoke runs (throwaway seeds 9100–9101, 300–600 ticks) to check the code works. Their outputs are not evidence, were deleted, and did not change this definition.

---

## Results
