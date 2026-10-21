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

## 2026-10-19 · stress test and optimization pass (D-036, D-037, D-038)

**A different machine from the entries above:** Linux x86_64 (4-core Intel Xeon @ 2.10 GHz with AVX-512, a cloud VM), Python 3.12.3, NumPy 2.5.4. Both columns below were measured in one session on this machine with nothing else running: *before* is commit `652165d` (end of Milestone 3) run through the same benchmark script, *after* is this branch. Same method as always: best of 3 repeats; `configs/default.yaml` population sweep with food scaled to N.

| target N | mean pop | mean food | ticks/s before | ticks/s after | µs per organism-tick before → after | speed-up |
|---:|---:|---:|---:|---:|---:|---:|
| 30 | 30 | 67 | 2326 | 2738 | 14.3 → 12.2 | 1.2× |
| 100 | 100 | 109 | 786 | 1203 | 12.7 → 8.3 | 1.5× |
| 300 | 300 | 160 | 214 | 595 | 15.6 → 5.6 | 2.8× |
| 1000 | 1000 | 260 | 41 | 152 | 24.6 → 6.6 | 3.7× |
| 3000 (100 ticks) | 3000 | 176 | 11 | 56 | 30.6 → 6.0 | 5.1× |

Cost per organism-tick no longer rises with population: the all-pairs distance tables that made it grow (D-017) are gone above ~4,000 pairs. The remaining ~6 µs is mostly per-organism Python (reading and writing the `Organism` objects) plus ~100 small NumPy calls per tick that every population size pays.

`configs/evolution.yaml` as the experiments run it (seed 9100, 5000 ticks, best of 2; `benchmark.py --evolution`):

| | before | after |
|---|---:|---:|
| simulation alone | 1662 ticks/s | 2233 ticks/s (1.3×) |
| with `RunRecorder` (gene statistics every tick, snapshots every 50) | 1265 ticks/s | 1833 ticks/s (1.4×) |
| recorder overhead | 31 % | 22 % |

A recorded 20,000-tick evolution run therefore takes ~11 s here instead of ~16 s (this VM is roughly 2.5× slower than the Apple Silicon laptop of the earlier entries).

**Profiles (cProfile, which inflates Python-call-heavy code; relative shares are what matter).**

| | before | after |
|---|---|---|
| N = 1000, 150 ticks | 4.3 s: `sense_food` 34 %, `resolve_feeding` 33 %, `step` body 15 %, `spend` 9 % | 1.4 s: `_grid_pairs` 41 % (half of it `argsort`), `step` body 10 % |
| N = 3000, 60 ticks | 6.9 s: `sense_food` 43 %, `resolve_feeding` 32 % | 1.3 s: `_grid_pairs` 40 %, `argsort` 31 % |
| evolution, 20,000 ticks (~94 organisms) | 28 s: `step` body 32 %, `spend` 16 % (5.6 M calls), `sense_food` 10 %, `resolve_feeding` 7 % | 16 s: `step` body 15 %, nearest-food 13 %, in-reach pairs 10 %, `move` 10 %, food `spawn`+`remove` 10 % |
| same, recorded | 38 s: recorder 25 % (24 reductions/tick, 12 M `getattr`, `asdict`) | 21 s: recorder 19 % |

Two lessons the profile taught: the fix that mattered at 1,000+ organisms (the grid) barely moves the realistic case, where Python call overhead dominated and array-based costs/deaths did the work; and after both, the floor is the fixed per-tick cost of ~100 NumPy calls, which only a wholesale restructuring would lower (declined, D-038).

**Stress pass, same machine** (`tests/test_stress.py`; the long ones under `pytest -m slow`):

| Scenario | Result |
|---|---|
| 5,000 organisms, 60 ticks, sim only / with recorder and events | 2.4 s / 2.4 s; 201 MB resident |
| 3,000 organisms with 1,500 food items: Python heap during a tick | well under 60 MB (all-pairs would need several 36 MB tables) |
| 50,000 ticks of `evolution.yaml` | 30 s; ledger drift at most 1.0e-8 EU = 0.002 of the tolerance; 8,853 organisms ever; 124 MB resident |
| 120 runs × 2,000 ticks, 3 workers, then `ingest` | 58 s, 120/120 ok; lake of 240 k tick rows and 1.44 M gene_stats rows; `count(*)` 14–17 ms, grouped medians 25 ms |
| Recorded 20,000-tick run with all events | recorder holds ~95 MB of row dicts (120 k gene_stats + 49 k events + 38 k genomes) |
| Extinction on tick 0; empty world kept ticking; caps of 1 and 2; all genes on a bound; one organism in a 3 × 2 world; 20,000 food items in a 2000 × 2000 world | all run, record, ingest and query correctly; nothing needed fixing |

**Bit-identity, verified not assumed:** every commit was checked against `tests/test_regression.py` (Linux state digests included) and against fifteen extra scenarios plus two complete recorded run folders recorded before the first change (state, event and energy digests; CSV bytes). All identical throughout.

## Neural brains (Milestone 4, 2026-10-19)

Apple Silicon (macOS 27, arm64), Python 3.12, simulation only (no recorder), 5,000 ticks, seed 9100, best of 3.

| Config | ticks/s | mean population | µs per organism-tick |
|---|---:|---:|---:|
| `evolution.yaml` (seeker, genes evolving) | 7,007 | 72.9 | 2.0 |
| `neural.yaml` with the controller swapped to the seeker | 6,333 | 88.5 | 1.8 |
| `neural.yaml` (brains decide) | 2,713 | 96.1 | 3.8 |

Brains roughly double the cost per organism-tick. A profile of 3,000 neural ticks puts **stacking every organism's brain into arrays each tick (`BrainStack.of`) at 24 %** of run time, against **6 % for the forward pass itself**; sensing and feeding take most of the rest, as for rule-based runs. The stack only changes when organisms are born or die, so caching it would be a bit-identical speed-up (same values, same arithmetic). Not done: a recorded 20,000-tick neural run takes ~10 s and E007's 144 runs took 34 s, so speed is not a constraint yet.

## 2026-10-21 · Milestone 6 review: predator and two-food worlds, and the brain-stack cache (D-065)

Linux x86_64 cloud VM (4-core Intel Xeon @ 2.80 GHz), Python 3.12.3, NumPy 2.5.4, simulation only, best of 3 repeats with nothing else running. "Before" is commit `ebaba2d`; "after" adds `BrainStackCache` (D-065). Crowds are the benchmark's recipe (population held at N, food scaled with N) with one predator per 25 prey where the config has them. Every digest was identical before and after.

| World | before, ticks/s | after, ticks/s | speed-up |
|---|---:|---:|---:|
| `neural.yaml`, seed 9100, 5,000 ticks (mean population 96) | 811 | 1,033 | 1.27× |
| `predators.yaml`, seed 1, 3,000 ticks (62 prey) | 623 | 708 | 1.14× |
| `predators-neural.yaml`, seed 1, 3,000 ticks (105 prey) | 612 | 719 | 1.17× |
| `neural.yaml` crowd, N = 1,000, 100 ticks | 65 | 76 | 1.17× |
| `predators.yaml` crowd, N = 1,000 + 40 predators, 100 ticks | 49 | 60 | 1.22× |
| `predators.yaml` crowd, N = 3,000 + 120 predators, 40 ticks | 17 | 21 | 1.24× |
| `diets.yaml`, seed 1, 3,000 ticks (no brains: measurement noise) | 1,028 | 1,145 | (1.11×) |

**Profiles before the cache (cProfile, which inflates Python-call-heavy code; shares of a tick are what matter).** A predator world makes five in-reach searches per tick (prey→food, predators→prey, prey→predators, meals, strikes), a two-food world four (the diet seeker senses each kind separately).

| World, N | ticks/s under cProfile | where the tick goes |
|---|---:|---|
| `predators.yaml`, 100 prey + 4 | 306 | `sense_food` ×3 28 %; `_grid_pairs` 23 % (argsort 5 %); `BrainStack.of` 14 %; `resolve_feeding`+strikes 12 %; `think` 10 % |
| `predators.yaml`, 1,000 prey + 40 | 38 | `_grid_pairs` 37 % (argsort 16 %); `BrainStack.of` 18 % (np.stack 13 %, 148 k `Brain.shape` calls 2 %); `np.unique` in `nearest_within_reach` 6 %; `forward` 3 % |
| `diets.yaml`, 100 | 546 | `_grid_pairs` 43 % (four searches); `_sense_kinds` 33 % of which the per-kind `sense_food` calls are most |
| `diets.yaml`, 1,000 | 88 | `_grid_pairs` 44 % (argsort 23 %); `_sense_kinds` 42 %; 154 k `_digests` calls 3 % |
| `predators.yaml`, 3,000 prey + 120 | 19 (cache on) | `_grid_pairs` 39 % (argsort 26 %), the three `sense_food` calls 61 % cumulative; `np.unique` 11 %; `BrainStackCache.of` 4 % (was `BrainStack.of` 18 % at 1,000) |
| `diets.yaml`, 3,000 | 30 | `_grid_pairs` 40 % (argsort 30 %); `_sense_kinds` 42 %; `np.unique` 12 % |

**Recording, ingest, report** (`evolution.yaml`, seed 9100, 5,000 ticks): simulation alone 1,972 ticks/s, with `RunRecorder` 1,419 ticks/s (overhead 39 % here; 22 % at D-038's measurement, on a quieter machine). The recorder holds its rows as dicts until the files are written: **3.9 KB per tick** (20 MB after 5,000 ticks; the slow suite's 120,000-tick export took the server from 359 to 1,383 MB resident). Under cProfile the recorder's time is `_stat_rows` 23 %, `decision_measures` 22 %, dict building the rest. `execute_run` 5.6 s of which `write_csv` 0.43 s; `ingest_run` 0.74 s (CSV read 0.27, primary-key group-by 0.11, Parquet write 0.07); `genesis report` 2.56 s for a 5.6 MB page (Plotly validation 0.6 s, `_number` parsing 0.35 s). A 20,000-tick predator run's report: 2.4 s, 5.3 MB. `genesis dashboard E008` (116 runs): 9.5 s. `genesis lake export --experiment E008` (12 tables): 16.8 s.

**Stress, Milestone 6 worlds** (`tests/test_stress.py`'s harness against a real uvicorn server, same machine):

| Scenario | Result |
|---|---|
| Four runs flat out, 15 s: `predators` s1, `diets` s2, `predators-neural` s3, and 2,000 prey + 80 predators | 94 / 133 / 94 / 16 ticks/s; GET /runs p50 191 ms, p95 230 ms, max 370 ms (a tick of the crowd is ~60 ms and runs round-robin); viewer of the crowd 63 frames of 94 KB, gaps p50 234 ms, p95 289 ms, max 296 ms; viewer of the diets run 63 frames of 5 KB; RSS 153 → 178 MB; nothing logged |
| 50 viewers at 30 fps on a predator run, target 200 ticks/s, 4 s | 2,130 frames delivered, peak 50 viewers, 0 after; heap +5.9 MB; **the run fell to 52 ticks/s** (the senders share the event loop with the stepping loop; clients were in the same process) |
| 50 viewers on a diets run, same | 2,153 frames, 50 / 0, heap +5.4 MB; **61 ticks/s** |
| History polling, `diets` 40,000 ticks flat out, since-polls every 0.5 s (every = 100) | 661 ticks/s; polls n = 107, p50 33.9 ms, p95 37.4 ms, max 40.8 ms; history 5.1 MB (128 B/tick); whole series (800 points) 11 ms; no nulls in food_a / diet_sd |
| History polling, `predators` 30,000 ticks (seed 7; prey extinct by ~3,300) | 3,445 ticks/s; polls p50 34.7 ms, max 513 ms (one poll hit the extinction's burst of deaths); history 3.4 MB (112 B/tick); predators column never null, diet columns always null |
| Export of the 40,000-tick diets run (replay + ingest) while an `evolution` run steps flat out | 200, matches live run, ingested, **231 s** (the live run took 60 s: the replay records and shares the GIL); the other run did 374 ticks/s meanwhile; GET /runs p50 30 ms, p95 39 ms, max 179 ms |
| Export of the 30,000-tick predator run, same | 200, matches, ingested, 18 s; other run 163 ticks/s; GET /runs p50 31 ms, max 59 ms |
| Lake queries during ingest: 6 threads over 5 lake routes (predator and diets series) while a predator run and a diets run step, export and ingest in a loop, 8 s | 410 requests, all 200; p50 93 ms, p95 209 ms, max 332 ms; 3 exports ingested; nothing logged |

What degrades: fifty 30-fps viewers cost a run three quarters of its target speed (every send runs on the simulation's thread); an export replays with the recorder in a worker thread and, with another run stepping, takes about four times the live run's time; a tick of a 2,000-organism world is ~60 ms, so with four flat-out runs any request can wait for a few of them.
