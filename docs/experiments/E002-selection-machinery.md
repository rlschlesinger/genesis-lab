# E002 · Does the evolution machinery work, and can selection be detected?

**Status:** defined 2026-10-18, before any E002 run. Results will be appended below the line without editing the definition.

## Why this experiment

Milestone 2 added genomes, mutation, inheritance and trade-off costs. Before asking open scientific questions (E003), we need evidence that:

1. With mutation off, genomes really stay identical (machinery check).
2. Selection can be told apart from drift, using a gene whose direction of selection we know in advance: **metabolic_rate**, which has no cost (a deliberate free lunch), so lower should win. This is the **positive control**: if the method can't detect *this*, it can't be trusted to detect anything.

## Design

| | |
|---|---|
| **Base config** | `configs/evolution.yaml` (mutation rate 0.1, size 0.05; drag exponent 1; sense cost 0.004; max_turn frozen; 20,000 ticks) |
| **Conditions** | **off**: mutation disabled. **neutral**: every gene `neutral: true` (inherited and mutating, but behaviour fixed at founders' values, so it shows drift alone). **selection**: the base config unchanged. |
| **Seeds** | 1000–1019 (20 per condition), shared across conditions. Never used before. |
| **Unit of analysis** | One run. |
| **Metric** | For gene *g* in run *r*: the population mean of *g* averaged over ticks 19,000–19,999 (`settled_gene_means`). |
| **Comparison** | Per seed: selection − neutral. Same seed means same founders and starting food, so each pair differs only in whether genes act. |
| **Stopping / extinction** | 20,000 ticks. Runs extinct before tick 19,999 are unmeasurable; their pairs are dropped and reported. If more than 4 of 20 pairs are dropped, the experiment is reported as inconclusive. |

### Why the neutral condition, not just the neutral marker

Under drift with reflection, a gene's mean moves toward the middle of its own range. The genes start at very different places within their ranges (speed 1.5 in [0.25, 4.0]; reproduction_threshold 80 in [55, 250]), so each has its own drift expectation. The neutral condition measures that expectation for every gene, from its real start, with identical mutation settings (decision D-025).

## Hypotheses

- **H6a (positive control, directional prediction):** metabolic_rate is **lower** under selection than neutral (selection − neutral < 0).
- **H6b, H6c, H6d:** speed, sense_range and reproduction_threshold differ between selection and neutral. **No direction predicted.** The seed-42 previews (increments 2.3–2.5) were run without a neutral comparison, so they can't predict a direction relative to it.

## Checks (pass/fail; not hypothesis tests)

- **C1 (machinery):** in all 20 **off** runs, every organism's genome equals the founders' and no mutations are recorded.
- **C2 (calibration):** neutral_marker is unexpressed in both conditions, so selection − neutral should show no systematic difference. Pass if the two-sided permutation p > 0.05. A small p would point to a bug, or to population-size effects on drift worth investigating.
- **C3 (drift expectation):** in **neutral** runs, report for each gene how many seeds moved toward the midpoint of its range.

## Analysis

- Per hypothesis: two-sided paired permutation test on the 20 per-seed differences. 2²⁰ sign patterns is too many to enumerate, so 20,000 are sampled using `numpy.random.default_rng(2002)`. Also reported: the sign test, the median difference and its range.
- **Holm correction** across H6a–H6d (4 tests). A hypothesis is **supported** if its adjusted p < 0.05 and, for H6a, the median difference is negative.
- Effect sizes are reported in gene units and as a fraction of the gene's range.
- Not tested: max_turn (frozen). neutral_marker is covered by C2.

## Limits stated in advance

- One parameter set. Selection and neutral populations may differ in size, which changes drift strength; the neutral condition approximates the drift expectation for a population that behaves like the founders.
- metabolic_rate may reach its floor (0.02), compressing differences.

---

## Results

### Protocol deviation (recorded before any results)

The first attempt, at the pre-registration commit `13a1561`, stopped with `EnergyLedgerError` before producing any results (E002: tick 13,820 of seed 1000 in the *off* condition; E003: tick 17,476). The cause was floating-point drift in the ledger's running totals, not an accounting error. It was fixed at commit `609c39b` (decision D-026). Simulation behaviour is unchanged (the ledger isn't part of the state; the golden regression tests pass). **No hypothesis, metric, seed, condition, window or analysis was changed, and no partial output was analysed.** All runs were re-executed from the commit that adds this note.

### Run

Commit `fb169c5` (clean; all 60 runs `dirty: false`), Python 3.12.13, NumPy 2.5.4, arm64 macOS. 60/60 runs completed 20,000 ticks; no extinctions, no pairs dropped. Raw files in `data/experiments/E002/` (not in Git; regenerate with `uv run python experiments/e002_selection_machinery.py`, re-analyse with `--analyse-only`).

### Checks

- **C1 (machinery): PASS.** 20/20 *off* runs: every genome equal to the founders', zero mutations recorded.
- **C2 (calibration): PASS.** neutral_marker selection − neutral: 9/11 split, permutation p = 0.55.
- **C3 (drift expectation):** neutral runs whose mean moved toward its range midpoint: metabolic_rate 9/20, speed 12/20, sense_range 7/20, reproduction_threshold 12/20. (neutral_marker 0/20 is uninformative: it starts at its midpoint, so it can't move closer. That's a flaw in how C3 was worded.) **Drift moved means little over 20,000 ticks:** neutral medians stayed near the founders' values (metabolic_rate 0.199, speed 1.54, sense_range 19.2, reproduction_threshold 82.0).

### Hypotheses: settled means, ticks 19,000–19,999

| | gene | neutral median | selection median | median S − N (of range) | +/− | sign p | permutation p | Holm-adjusted | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| H6a | metabolic_rate | 0.199 | 0.037 | −0.160 (−33.2%) | 0/20 | 1.9e-6 | ≤ 5e-5* | 0.0002 | **supported** (lower, as predicted) |
| H6b | speed | 1.54 | 2.03 | +0.61 (+16.3%) | 18/2 | 0.0004 | ≤ 5e-5* | 0.0002 | **supported** (higher) |
| H6c | sense_range | 19.19 | 19.95 | +1.09 (+1.8%) | 12/8 | 0.50 | 0.78 | 0.78 | not supported |
| H6d | reproduction_threshold | 82.0 | 91.1 | +11.7 (+6.0%) | 14/6 | 0.12 | 0.0056 | 0.011 | **supported** (higher) |

\* None of the 20,000 sampled sign patterns was as extreme; with the +1 correction, 1/20,001 ≈ 5e-5 is the smallest value this analysis can report.

### Interpretation

- **The positive control worked:** the cost-free gene evolved in the predicted direction in every seed, against no drift trend. The method can detect selection.
- **Selection favoured faster organisms (18/20)** and **higher reproduction thresholds**. The threshold result rests on the pre-registered permutation test; the sign test alone (14/20) would not reach significance, so a few seeds with large differences carry it.
- **Sense range:** no detectable selection relative to drift. Not evidence that none exists.
- **Observation, not a tested prediction:** the selected speed (median 2.03) is close to the speed that minimises energy per unit distance under these costs (~2.05, increment 2.4 exercise). Testing that link needs its own pre-registered experiment (for example, varying the drag exponent and predicting the shift).

### Corrections to earlier statements

- D-025 and increment 2.4–2.5 commentary suggested drift would pull reproduction_threshold strongly upward (toward 152) and that selection might be holding it down. Over 20,000 ticks, drift moved it only from 80 to ~82, and selection raised it relative to drift. The neutral twin remains the right control; it showed the drift effect was small.

### Limits observed

Settled population: neutral median 89 (85–93), selection median 102 (58–177). Similar depth of ancestry (median maximum generation 72 vs 70.5). The size difference means drift strength wasn't identical between conditions; the effects above are large relative to the neutral marker's spread, so this is unlikely to explain them, but it isn't formally excluded.
