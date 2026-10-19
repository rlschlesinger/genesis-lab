# Decision log

Each entry records a decision, why it was made, and what would make us revisit it.

## D-001 · Use uv for Python and dependency management (2026-10-18)

**Decision:** uv manages the Python version, virtual environment and lockfile (`uv.lock`).
**Why:** one tool, fast, produces a cross-platform lockfile for reproducibility.
**Alternatives:** pip + venv + pip-tools (more pieces), Poetry (slower, separate Python management), conda (heavier).
**Revisit if:** a required package is only distributed via conda.

## D-002 · Defer Mesa; write our own simulation loop (2026-10-18)

**Decision:** Milestone 1 does not use Mesa.
**Why:** Mesa's model is agents that act one at a time in a shuffled order. Our spec requires snapshot observation and simultaneous resolution, which would work against that. Mesa's main extras (Solara visualization, batch runner) overlap with our planned React UI and experiment tooling. Writing the loop is also more instructive.
**Revisit at:** Milestone 3, when building batch experiments.

## D-003 · Exact-copy reproduction in Milestone 1 (2026-10-18)

**Decision:** organisms reproduce by cloning their `Traits` exactly; mutation arrives in Milestone 2.
**Why:** without reproduction the population can only decline, which leaves the ecosystem untested. Cloning lets us check ecological dynamics (for example, does population settle near what the food supply can sustain?) before evolution adds variation.

## D-004 · Hard-wall boundaries (2026-10-18)

**Decision:** the world is bounded; positions are clamped to the edges.
**Why:** matches the spec ("bounded"). Wrap-around (torus) can be added later as a config option if edge effects become a confound.

## D-005 · Food contention rule (2026-10-18)

**Decision:** if several organisms can eat the same food in one tick, the closest wins; exact ties are broken by a dedicated seeded RNG stream.
**Why:** breaking ties by organism ID would systematically favour older lineages and bias evolution.

## D-006 · Independent RNG streams per subsystem (2026-10-18)

**Decision:** one run seed → `SeedSequence.spawn` → separate generators for food, controllers, reproduction and tie-breaking.
**Why:** keeps subsystems from shifting each other's random sequences, so paired-seed experiments stay comparable as code changes.
**Limit:** bit-identical results are guaranteed only within the same machine, OS and package versions.

## D-007 · YAML files validated by Pydantic (2026-10-18)

**Decision:** configs are YAML, read with `yaml.safe_load`, validated into frozen Pydantic models that forbid unknown keys.
**Why:** a typo or impossible value should stop a run before it starts, with an error naming the field. Frozen configs can't drift mid-run.
**Alternatives:** TOML via the standard library's `tomllib` (no dependency, but the spec names YAML); dataclasses with hand-written checks; `msgspec`.

## D-008 · Reproduction energy split (2026-10-18)

**Decision:** reproducing costs the parent `offspring_energy + reproduction_overhead`; the child receives `offspring_energy`; the overhead is lost.
**Why:** makes reproduction costly (as the spec requires) while keeping the energy ledger explicit. A config is rejected if reproducing could drive the parent to zero.

## D-009 · Poisson food regrowth (2026-10-18)

**Decision:** new food per tick ~ Poisson(`regrowth_per_tick`), capped at `max_count`, at uniformly random positions.
**Why:** the standard model for independent events at a constant average rate; supports fractional rates (0.3/tick) naturally.
**Alternatives:** a deterministic accumulator (adds exactly 0.3 per tick, spawns when it passes 1). It's less noisy, but its regular timing could become an artefact organisms exploit. We could revisit it as a config option.
**Note:** the Poisson draw happens even when food is at the cap, so the food stream's sequence doesn't depend on how much was eaten.

## D-010 · Food stored as a NumPy array, not objects (2026-10-18)

**Decision:** `FoodSupply` holds an `(n, 2)` float64 array.
**Why:** food has no state beyond its position, and sensing needs distances to all food every tick, which is a single vectorized operation on an array.
**Revisit if:** food gains per-item state (e.g. varying energy, decay). Then add parallel arrays first, and objects only if needed.

## D-033 · Experiment dashboards show runs and summaries separately (2026-10-19)

**Decision:** one HTML dashboard per experiment from the lake. Runs are faint lines and small dots; summaries are bold medians with a middle-50% band, or medians and mean differences with 95% bootstrap CIs. Median-over-time points carry their run count.
**Why:** the scope requires distinguishing individual runs from aggregates; a single line per condition hides replicate variation, and raw lines hide the pattern. Spread (middle 50%) and precision (CI) answer different questions and are labelled as such. Run counts expose survivorship bias when runs go extinct.
**Verified:** in Chrome at 1280 px and 390 px (offline, no horizontal scroll). A phone-width screenshot showed rotated pair labels running into subplot titles, fixed with two-line labels and more spacing.
**Alternatives:** mean ± SE error bars only (hides individual runs and skew); box plots (hide n and individual runs at n = 20); one subplot per run (unreadable at 80 runs).

## D-032 · pandas and SciPy for analysis; estimation alongside testing (2026-10-19)

**Decision:** pandas 3.0.6 for tables in Python (results arrive from DuckDB via `.df()`); SciPy 1.18.1 as an independent reference. New tools in `analytics/analysis.py`: percentile bootstrap CIs, Wilson intervals, paired effect sizes, and a SESOI-based practical-significance verdict. The hand-written tests stay; SciPy cross-checks them.
**Evidence:** sign test = `scipy.stats.binomtest` in all 39 cases; exact paired and equal-group permutation tests = `scipy.stats.permutation_test` to 1e-12; Wilson = SciPy's to 1e-12; bootstrap interval covered the true mean in 90–98% of 400 simulated datasets.
**Why:** p-values say whether an effect is distinguishable from zero, not how big or how precisely known it is; intervals and effect sizes answer that, and a pre-stated SESOI turns "significant" into "matters / doesn't / don't know yet".
**Alternatives:** BCa bootstrap (better coverage at small n; more complex to explain); statsmodels (adds Holm and regression; not needed yet); Polars (faster DataFrames; less teaching material).

## D-031 · Experiment spec files and a parallel, resumable runner (2026-10-19)

**Decision:** experiments are YAML spec files run by `genesis experiment run`; runs execute in a process pool; completed runs with the same config hash are skipped; completed runs with a different hash ("stale") stop the batch unless `--rerun-stale`.
**Why:** one runner instead of a script per experiment; parallelism cuts wall time ~7× on this machine with byte-identical results; resume makes interruptions cheap; refusing stale runs prevents silently mixing two versions of an experiment. Processes, not threads: Python runs one thread of Python code at a time (the GIL), so threads wouldn't speed up CPU-bound simulation.
**Consequence:** a config field added later (even one that doesn't affect results, like recording settings) makes older runs stale. That is deliberate: "same config" is checked literally, never by judgement.
**Alternatives:** threads (no speed-up here); a job queue or workflow tool (Snakemake, Prefect: more infrastructure than one machine needs); comparing configs ignoring "result-neutral" fields (needs a judgement call per field, easy to get wrong).

## D-030 · DuckDB views created on connect (2026-10-19)

**Decision:** `connect()` returns an in-memory DuckDB connection and defines every view each time (a view per lake table, derived views, a table macro, and an `experiments` table built from the experiment documents and git history). A database file is optional (`genesis lake rebuild-db`) and uses absolute paths.
**Why:** views store no data, so creating them costs milliseconds and they can never be stale; no database file has to be kept in sync with the lake. DuckDB resolves relative Parquet paths against the working directory, not the database file, so a persistent file needs absolute paths.
**Verification:** SQL results are compared with independent plain-Python computations from the CSVs (not pandas, which arrives in 3.5: an even more independent check); the documented examples are executed by the tests; two views were deliberately broken to confirm the tests catch it.
**Alternatives:** a persistent database with data loaded into native tables (faster repeated queries; a second copy to keep in sync); SQLite (can't read Parquet; built for transactions, not scans).

## D-029 · ETL design (2026-10-19)

**Decision:** pyarrow reads each CSV with stated column types (never inferred), writes one zstd Parquet file per run per table, and only after every check passes. Failed runs get a `runs` row only. Timestamps are microseconds (UTC). A run failing any check is refused whole and nothing of it is written; a bug inside a check crashes the batch rather than being skipped.
**Why:** stated types make "a count read as text" impossible; per-run files make ingestion repeatable and incremental; all-or-nothing loading means the lake never holds half a run. Parquet has no second-precision timestamp (pyarrow silently widened "s" to "ms", caught by the schema test), and microseconds match DuckDB. A checker that quietly skipped on error would look exactly like one that passed.
**Measured:** 165 runs back-filled in 8.7 s, 206 MB from ~1.94 GB of CSV, none refused.
**Alternatives:** pandas `to_parquet` (type inference, less control); DuckDB `COPY ... TO` (checks written in SQL before SQL is taught); one large file per table (re-ingesting a run would rewrite everything).

## D-028 · Sampled tick rows sum flows; optional event log (2026-10-19)

**Decision:** `recording.ticks_every` keeps every n-th tick (plus the final tick) in ticks.csv and gene_stats.csv. Stock columns are snapshots of the recorded tick; flow columns are totals since the previous recorded row. `recording.events` logs births, deaths and/or meals to events.csv. run.json gains `schema_version` (3), `condition`, `config_hash`, `ticks_every`, `events_recorded`.
**Why:** plain sampling would keep one tick's births out of every n and silently undercount totals by (n−1)/n; summing flows keeps totals exact at any interval (demo: identical totals at 1 and 10, with 10× fewer rows). Events support questions per-tick totals can't answer (where deaths happen, birth-time population), at modest size (~0.6 MB per 20k-tick run for births and deaths). Condition and config hash make runs groupable and comparable in the database.
**Defaults:** `ticks_every: 1`, no events: output identical to schema version 2 apart from the new run.json fields and a header-only events.csv; golden tests unchanged.

## D-027 · Golden values: state digests per platform, event digests everywhere (2026-10-19)

**Problem:** on a fresh Linux x86_64 checkout, `tests/test_regression.py` failed at every commit since the golden digests were recorded, including the commit that recorded them. Nothing in the code had changed behaviour: on this machine NumPy's `hypot` and `arctan2` give results that differ in the last bit from the arm64 macOS machine the values came from (on x86_64 with AVX-512, NumPy uses its own vectorised implementations; 0.6% of `hypot` and 7.8% of `arctan2` results differ from the C library's in the last bit). `state_digest()` hashes every float bit for bit, so one such difference anywhere changes it. D-006 already warned that bit-identical results hold only on one machine; the golden test had no way to say so.
**Evidence that only the bits differ, not what happens:** E001's per-run metrics for seeds 0 and 1, both controllers (capacity, t90, standing food, median lifespan, lineages over 5,000 ticks) reproduce the recorded arm64 values exactly on Linux. In these runs, a last-bit difference didn't change who reached food first or who starved. That is observed, not guaranteed: the dynamics are sensitive to small differences, so long runs (E002/E003's 20,000 ticks) may diverge event by event across platforms while their statistical conclusions should still hold. Exact replication of a recorded run should be done on the platform recorded in its run.json.
**Decision:** two kinds of golden value. *State digests* are kept per `(system, machine)` platform and checked only on a platform with recorded values (skipped elsewhere, with the reason shown). *Event digests*, a SHA-256 over every tick's integer counts (population, births, deaths, food counts, meals, lineages, mutations), are checked on every platform. A state failure with an event pass means rounding changed; an event failure means behaviour changed.
**Limits:** `(system, machine)` is a proxy for what actually decides the bits (CPU features, NumPy build, C library). A different x86_64 Linux CPU could fail the state test while passing the event test; that is the documented, benign case. Full bit-portability would need replacing `hypot`/`arctan2` with arithmetic that is correctly rounded everywhere, which changes behaviour and is not attempted.
**Alternatives:** one set of golden values plus a tolerance (a tolerance on a hash is meaningless; on raw state it needs a reference run checked into Git); skipping the whole file off-platform (loses all cross-platform protection).

## D-026 · Ledger: exact per-tick sums; tolerance scaled to energy flowed (2026-10-18)

**Problem:** the first E002/E003 runs (commit `13a1561`) stopped with `EnergyLedgerError`: +3.5e-6 EU at tick 13,820 (E002, mutation off, seed 1000) and −2.7e-6 EU at tick 17,476 (E003). No accounting was wrong. Millions of small payments added one at a time to running totals near 10⁶ each lost a rounding sliver, and the drift outgrew a tolerance scaled to the current *stock* (~3,500), while ~1.1 M EU had flowed through (314x the stock).
**Decision:** (1) sum each tick's payments per flow exactly with `math.fsum` and add once per tick; (2) tolerance = 1e-6 + 1e-12 × gross flow.
**Evidence:** worst drift over four full 20,000-tick runs after (1): ~6e-9 EU, ≤ 4e-15 of gross flow (600x smaller than the failure). The tolerance (2.6e-6 at 1.6 M gross) is ~450x above that and ~1500x below the smallest real error (one missed 0.004 EU sensing payment). The old drift would still be rejected: the fix is (1), not a looser check.
**Simulation behaviour unchanged:** the ledger isn't part of the state; golden regression tests pass.

## D-025 · Neutral-twin controls instead of the neutral marker alone (2026-10-18)

**Decision:** a per-gene `neutral` flag: the gene is inherited and mutates, but `express()` uses its initial value. Selection is judged by comparing normal runs with all-neutral runs on the same seeds.
**Why:** under reflected drift, each gene's mean drifts toward the middle of *its own* range, and genes start at different places (reproduction_threshold 80 in [55, 250] would drift strongly upward). The neutral marker starts mid-range, so it can't give the drift expectation for other genes. Without this, the seed-42 rise in threshold (80 → 105) could have been misread as selection for higher thresholds, when drift alone might push it higher still.
**Consequence:** E002 and E003 compare selection − neutral per seed; E003 uses a difference of differences.
**Alternatives:** compare each gene with the marker after rescaling (doesn't fix the different starting points); start every gene mid-range (changes founders, breaks Milestone 1 continuity).

## D-024 · Hand-written permutation and sign tests (2026-10-18)

**Decision:** `significance.py` implements an exact sign test, exact/sampled paired and two-group permutation tests, and the Holm correction, with NumPy and the standard library only.
**Why:** few assumptions (no normality needed, suits 10–20 runs), every step is visible for learning, and no new dependency (SciPy stays in Milestone 3). Tested against hand-computed answers, and calibrated: under a true null, about 5% of p-values fall below 0.05.
**Alternatives:** t-tests (assume roughly normal differences); SciPy's `permutation_test` / `binomtest` (equivalent, adopted later for cross-checking).

## D-023 · HTML run reports with Plotly (2026-10-18)

**Decision:** `genesis report` writes one self-contained HTML file per run, using Plotly 7.1.0 (embedded once, ~6 MB), a custom dark "instrument" theme with system fonts, and fixed chart IDs for deterministic output. Charts are downsampled to ≤2000 points per line by fixed stride. Built only from recorded files.
**Why:** interactive charts (hover, zoom) from the spec's stack; offline and shareable as one file; re-plottable from any past run. Deterministic output keeps reports reproducible like everything else.
**Alternatives:** matplotlib PNGs (static, small); loading Plotly from a CDN (1/10 the size, needs a network); a web app (Milestone 5).
**Verified:** rendered in Chrome at 1280 px and 390 px (no horizontal scroll), and with the network disabled.

## D-022 · Trait statistics and genome snapshots (2026-10-18)

**Decision:** a `RunRecorder` in analytics writes `gene_stats.csv` (tidy: tick, gene, n, mean, population sd, min, max, every tick) and `genomes.csv` (every living genome every `recording.genome_snapshot_every` ticks, default 50, plus the final tick).
**Why:** trends need every tick; distributions need individual values, which would be ~2.6M numbers per run at every tick. Tidy format suits pandas, DuckDB and Plotly. Keeping recording out of `Simulation` keeps the core free of I/O policy.
**Measured cost:** ~16 MB per 20,000-tick run (10 MB of it gene_stats.csv). Revisit (sample stats every k ticks, or Parquet in Milestone 3) if batches grow large.

## D-021 · Trade-off costs and the evolution config (2026-10-18)

**Decision:** a sensing upkeep (`sense_cost_per_unit × sense_range` per tick) and drag on movement (`× (speed / founder speed) ^ exponent`). Metabolic rate stays cost-free as the positive control. `max_turn` is frozen in `evolution.yaml` because turning has no cost and would be a second free lunch. Evolution settings live in `configs/evolution.yaml`, a full copy of `default.yaml` with a test restricting the differences.
**Why:** without costs, every beneficial gene slides to its bound, which is an artefact, not a finding. Costs create optima that can depend on the environment. Making drag relative to the founders' speed keeps founders' costs identical to Milestone 1, so only mutants feel the change.
**Values:** exponent 1 (cost/tick at full speed ∝ speed²); sense cost 0.004 (founders +0.08/tick, +23%). Chosen to be noticeable but not dominant; not tuned to produce any particular outcome.
**Alternatives:** a turning cost (would let max_turn evolve; more mechanism to justify); YAML includes/inheritance instead of a copy (less duplication; adds a config feature).

## D-020 · Genes in the state digest; how golden values were updated (2026-10-18)

**Decision:** `state_digest()` now includes every organism's genes.
**Why:** an unexpressed gene (the neutral marker) never affects behaviour, so two runs differing only there would otherwise get identical digests forever.
**Procedure (to keep the golden tests anchored to E001):** first wire mutation in and confirm the *old* golden digests still match with mutation off (behaviour unchanged); only then change the digest definition and record new golden values. The chain is documented in tests/test_regression.py. Digests in run.json files from before this change aren't comparable with later ones.

## D-019 · Mutation rule (2026-10-18)

**Decision:** per gene, per birth: mutate with probability `rate`; step ~ Normal(0, `size × range`); reflect at the bounds. Every birth makes the same number of draws from a dedicated `mutation` stream (appended last). Per-gene `mutable` flag. Disabled by default.
**Why:** a normal step with mean 0 has no built-in direction, so trends must come from selection or drift. Scaling to each gene's range makes one `size` meaningful for all genes. **Reflection, not clamping:** clamping parked 13% of 2000 neutral lineages exactly on a bound after 300 generations (demo, 2.2), a fake "selection for extremes"; reflection stayed flat with none on a bound. Constant draws per birth keep the stream independent of outcomes. `mutable` lets experiments isolate one gene.
**Alternatives:** multiplicative/log-scale steps (suits strictly positive traits; consider if small values matter); resampling out-of-range steps (also unbiased, but a variable number of draws).

## D-018 · Genome representation (2026-10-18)

**Decision:** `Genome` is a frozen dataclass with one float per gene, stored in trait units. `express()` maps it to `Traits`. Gene limits come from the config's `genome` section; units and descriptions live in `GENES`. All founders share one genome.
**Why:** rescaling genes to 0–1 and back can change values by one rounding step, which would have changed Milestone 1 results (the golden test would fail). Named fields are clearer to read and inspect than an array. Identical founders mean any variation is attributable to mutation.
**Alternatives:** 0–1 normalized genes (uniform mutation scale; rounding problem); a NumPy array (faster en masse, less readable); initial standing variation (a possible config option later).
**Consequence:** the config's `organisms.traits` section was replaced by `genome`. Configs from Milestone 1 need migrating; behaviour is unchanged (verified by tests/test_regression.py).

## D-017 · No performance optimization in Milestone 1 (2026-10-18)

**Decision:** keep the all-pairs distance calculations in sensing and feeding.
**Why:** measured, not guessed (docs/benchmarks.md). A default run takes ~1 s; 1000 organisms runs at 140 ticks/s. The profile shows the two n × m distance computations take ~75% of the time at N = 1000, so that's where a future fix would go.
**Revisit when:** an experiment needs populations of 1000+, or batch sizes make run time a bottleneck. Planned fix: a spatial index.

## D-015 · Run output format for Milestone 1 (2026-10-18)

**Decision:** each run writes `run.json` + `ticks.csv` + `organisms.csv`, using only the standard library. run.json carries status (running → completed / failed) and provenance (git commit + dirty flag, versions, platform, full config). Files are written atomically (temp file + rename).
**Why:** human-readable, needs no new dependencies, and enough for Milestone 1's question. Writing status first means crashed runs leave evidence.
**Alternatives:** Parquet + DuckDB (planned for Milestone 3, once there are many runs to query); SQLite.
**Revisit at:** Milestone 3.

## D-016 · Founder lineage tracking (2026-10-18)

**Decision:** every organism carries `founder_id`; the `lineages` metric counts distinct founder lineages alive.
**Why:** spec section 9 asks for lineage diversity indicators. Measured before mutation exists, it gives the size of pure-chance drift, which Milestone 2 must distinguish from selection.

## D-014 · Reproduction details (2026-10-18)

**Decision:** one child per parent per tick; random parent choice when the population cap binds; offspring placed uniformly within one step (`speed`) of the parent.
**Why:** the list is in ID order, so "first come first served" at the cap would always favour the oldest lineages, a hidden selection pressure that would distort Milestone 2. Uniform-in-disc placement (via a square root on the radius) avoids clustering births at the parent's exact position.
**Alternatives at the cap:** highest energy first (a deliberate selection rule; could be an experimental condition later).

## D-013 · Feeding rules (2026-10-18)

**Decision:** one meal per organism per tick; in-reach pairs resolved closest-first with random tie-breaking; eating happens before costs are paid.
**Why:** one meal per tick bounds the rate of energy intake. Closest-pair matching implements "closest wins" while still feeding every organism it can. Eating first means an organism that reaches food doesn't die from a cost paid an instant earlier.
**Alternatives:** split contested food between contenders (no winner, but fractional food complicates the ledger); an optimal assignment to maximize meals eaten (harder to explain, and no biological reason).
**Observed consequence (seed 42, no reproduction yet):** energy accumulates without bound (mean ~5000 EU by tick 5000 for seekers). Expected to be absorbed by reproduction in 1.7. If it isn't, consider a maximum energy trait.
**Update (1.7):** confirmed resolved. With reproduction, mean energy settles around 35 EU (seed 42, both controllers).

## D-012 · A fifth RNG stream for setup; streams are append-only (2026-10-18)

**Decision:** founder placement gets its own `setup` stream. Streams are spawned in a fixed order, and a new one is only ever added at the end.
**Why:** borrowing another stream for founder placement would shift that stream's sequence. `SeedSequence.spawn` hands out child seeds in order, so inserting a stream in the middle would silently change every stream after it, and with it every result from earlier software versions.

## D-011 · Energy left at death leaves the system (2026-10-18)

**Decision:** energy an organism still holds when it dies (e.g. of old age) is removed and recorded in the energy ledger as "lost at death".
**Why:** the simplest choice that keeps accounting exact.
**Alternatives:** convert it into food at the death location (a "carcass": recycles energy, enables scavenging); share it among nearby organisms.
**Revisit:** a carcass option makes a good Milestone 6 ecology experiment.
