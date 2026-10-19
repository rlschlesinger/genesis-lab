# Benchmarks

Recorded results of `uv run python experiments/benchmark.py`. Re-run and add a dated section after performance-relevant changes; never edit old entries.

## 2026-10-18 · commit `b7ca35c` (end of increment 1.8)

Apple Silicon (arm64) macOS, Python 3.12.13, NumPy 2.5.4. 200 ticks per repeat, best of 3. Population held near N (initial_count = max_population = N; food scaled with N).

| target N | mean pop | mean food | ticks/s | µs per organism-tick |
|---:|---:|---:|---:|---:|
| 30 | 30 | 67 | 7664 | 4.3 |
| 100 | 100 | 109 | 2497 | 4.0 |
| 300 | 300 | 160 | 720 | 4.6 |
| 1000 | 1000 | 260 | 140 | 7.1 |

**Profile at N = 1000** (cProfile, cumulative time): `resolve_feeding` 39%, `sense_food` 36%, `Organism.spend` 6%, `_reproduce` 1%. Both hotspots compute all n × m organism–food distances, so per-organism cost rises with food count.

**In practice:** a default 5000-tick run (~110 organisms) takes ~1 s; E001's 20 runs took 44 s.

**Decision:** no optimization now (D-017). If experiments need populations of 1000+, the known fix is a spatial index (grid buckets, or `scipy.spatial.cKDTree`) so each organism checks only nearby food.

## 2026-10-18 · commit `fdcfefa` (end of Milestone 2)

Same machine and method as above (`configs/default.yaml` population sweep).

| target N | mean pop | mean food | ticks/s | µs per organism-tick | vs Milestone 1 |
|---:|---:|---:|---:|---:|---:|
| 30 | 30 | 67 | 6934 | 4.8 | −10% |
| 100 | 100 | 109 | 2277 | 4.4 | −9% |
| 300 | 300 | 160 | 646 | 5.2 | −10% |
| 1000 | 1000 | 260 | 129 | 7.8 | −8% |

`configs/evolution.yaml` (mutation and trade-offs on, seed 9100, 5000 ticks, best of 2): **4726 ticks/s** simulating alone, **3548 ticks/s** with `RunRecorder` (gene statistics every tick plus snapshots, ~25% overhead). A 20,000-tick recorded evolution run takes ~6 s; E002 + E003 (140 runs, two processes) took ~15 minutes.

**Where the ~10% went:** per-organism genome/trait handling, the cost functions, and building per-tick payment lists for the exact ledger sums (D-026). No optimization needed yet (D-017 still applies).

## 2026-10-19 · commit `aee1017` (end of Milestone 3): data pipeline

Same machine. Lake: 495 runs (E001–E006 plus stand-alone runs), 293 MB in 3,236 Parquet files.

| Operation | Time |
|---|---:|
| Full ingest of every run folder into a new lake (`genesis lake ingest`, 495 runs) | 14.7 s |
| `connect()`: define every view and macro | 0.11 s |
| `count(*)` over all 25.5 M `gene_stats` rows | 33 ms |
| `settled_gene_means(19000, 19999)` over the whole lake (1,098 run × gene rows) | 40 ms |
| Organisms × ticks join on (run_id, birth tick), 846 k rows | 112 ms |
| E003 per-condition median (SQL example 4) | 79 ms |
| Experiment dashboard, E003 with two paired panels | 4.1 s |
| Export E003 (13.7 M rows, Parquet) | 1.7 s (3.7) |
| Batch runner: 12 runs of 5,000 ticks on 1 vs 13 workers | 17.5 s vs 2.6 s (3.4) |

Simulation throughput is unchanged from the end of Milestone 2 (Milestone 3 added no simulation code beyond event collection, which tests show doesn't change results).
