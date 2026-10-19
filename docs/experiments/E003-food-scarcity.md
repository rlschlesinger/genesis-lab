# E003 · Does food scarcity change what selection favours?

**Status:** defined 2026-10-18, before any E003 run. Results will be appended below the line without editing the definition.

## Question

When food is scarce, does selection push the evolving genes differently than when food is plentiful, beyond any difference drift alone would cause?

## Design: 2 × 2, paired by seed

| | plentiful food (regrowth 2.0) | scarce food (regrowth 1.0) |
|---|---|---|
| **selection** (base config) | S_plenty | S_scarce |
| **neutral** (all genes `neutral: true`) | N_plenty | N_scarce |

| | |
|---|---|
| **Base config** | `configs/evolution.yaml` |
| **Independent variable** | `food.regrowth_per_tick`: 2.0 (control) vs 1.0 |
| **Why 1.0** | Feasibility pilot on seeds 9001–9003 (population and extinction only, no gene data viewed): all survived, minimum population after tick 2000 was 18–28. At 0.75 the minimum dropped to 15. |
| **Seeds** | 2000–2019 (20), shared across all four conditions. Never used before. |
| **Metric** | Per gene and run: population mean over ticks 19,000–19,999 (as in E002). |
| **Extinction** | A seed is dropped if any of its four runs is unmeasurable; drops are reported. More than 4 of 20 dropped means inconclusive. |

### The comparison: difference of differences

Scarcity changes population size and generation time, and with them how fast drift acts. So comparing S_scarce with S_plenty directly would mix up selection and drift. Instead, for each seed and gene:

- selection effect with plentiful food: `S_plenty − N_plenty`
- selection effect with scarce food: `S_scarce − N_scarce`
- **interaction** = scarce effect − plentiful effect

A non-zero interaction means scarcity changes what selection does, after removing each food level's own drift.

## Hypotheses (two-sided tests; directions where predicted, with reasons)

- **H7a (sense_range), predicted interaction > 0:** sparser food makes seeing farther worth more relative to its fixed upkeep (0.004 EU per unit of range per tick).
- **H7b (speed), no direction predicted:** scarcity raises the value of covering ground but tightens the energy budget that drag draws on.
- **H7c (reproduction_threshold), no direction predicted:** a higher reserve may buffer longer gaps between meals, but slower reproduction costs more when lineages compete for few resources.
- **H7d (metabolic_rate), predicted no detectable interaction:** it is likely near its floor (0.02) in both food levels (a floor effect). A non-significant result here is *not* evidence that scarcity has no effect on metabolism.

## Analysis

- Per hypothesis: two-sided paired permutation test on the 20 per-seed interactions, 20,000 sampled sign patterns from `numpy.random.default_rng(2003)`. Also reported: sign test, median and range of the interaction, and each food level's selection effect on its own.
- **Holm correction** across H7a–H7d. Supported if the adjusted p < 0.05 and, where a direction was predicted, the median interaction has that sign.
- Reused check from E002: neutral_marker's interaction should not be significant (calibration).

## Limits stated in advance

- Two food levels, one parameter set. Effects may not hold at other scarcity levels or cost settings.
- A "neutral" population behaves like the founders, so it may differ in size from the evolving one; the difference-of-differences design reduces, but doesn't remove, this concern.

---

## Results

### Protocol deviation (recorded before any results)

The first attempt, at the pre-registration commit `13a1561`, stopped with `EnergyLedgerError` before producing any results (E002: tick 13,820 of seed 1000 in the *off* condition; E003: tick 17,476). The cause was floating-point drift in the ledger's running totals, not an accounting error. It was fixed at commit `609c39b` (decision D-026). Simulation behaviour is unchanged (the ledger isn't part of the state; the golden regression tests pass). **No hypothesis, metric, seed, condition, window or analysis was changed, and no partial output was analysed.** All runs were re-executed from the commit that adds this note.
