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
