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

### Run

Commit `8ea2000` (clean; all 250 runs `dirty: false`). 250/250 completed (162 by extinction, 88 reaching tick 3,000). Analysis: `uv run python experiments/e006_founders_extinction.py --analyse-only`. Dashboard: `uv run genesis dashboard E006`.

### Extinction by founder count (95% Wilson interval)

| founders | extinct | proportion | 95% CI | median tick of extinction (range) |
|---:|---:|---:|---|---|
| 2 | 38/50 | 0.76 | [0.63, 0.86] | 274 (142–2,565) |
| 5 | 24/50 | 0.48 | [0.35, 0.61] | 522.5 (177–2,672) |
| 10 | 25/50 | 0.50 | [0.37, 0.63] | 638 (200–2,955) |
| 20 | 39/50 | 0.78 | [0.65, 0.87] | 575 (235–2,807) |
| 40 | 36/50 | 0.72 | [0.58, 0.83] | 416.5 (210–2,988) |

### Hypotheses

- **H10: NOT SUPPORTED.** Correlation between log₂(founders) and extinction = **+0.051**, permutation p = **0.42**. There is no evidence that extinction falls as founders increase.
- **Practical significance: inconclusive.** P(extinct | 2) − P(extinct | 40) = **0.04**, 95% CI [−0.14, 0.22]: the interval includes 0 and also reaches past the SESOI (+0.15), so neither "no difference" nor "a meaningful decrease" can be ruled out.

### Interpretation

The pre-registered prediction failed. The risk stated in advance (low carrying capacity, about 6 organisms) may explain part of it, but the data show something more specific.

**Exploratory (post hoc, not tested):** extinction looks **U-shaped** in founders: high at 2 (0.76), lowest at 5–10 (about 0.5), high again at 20–40 (0.72–0.78). The 2-founder and 5-founder intervals barely overlap, as do the 10- and 20-founder ones. Timing points the same way: 2-founder groups die earliest (median tick 274); intermediate groups last longest. A plausible mechanism: tiny groups fail by bad luck before they find food (demographic stochasticity), while large groups in a world with **no starting food** all deplete their energy competing for 0.1 items per tick, then crash together. Both ends lose; the middle is safest.

This is a hypothesis generated by the data, not a finding. Testing it needs a fresh, pre-registered experiment: for example, more founder levels, new seeds, a stated U-shaped model (a quadratic term in log founders), and a variant with some starting food, where the large-group penalty should disappear if the mechanism is right.
