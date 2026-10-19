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

## D-045 · E007's machinery: given founder brains, per-condition seeds, neural golden values (2026-10-19)

**Decision:**
- `brain.founder_weights`: an optional list of 62-number vectors, one per founder (validated: count = `initial_count`, length 62, finite, within ±`weight_limit`). Founders take exactly these brains and nothing is drawn from the brain stream. The weights live in the config, so `config_hash` and run.json identify the exact brains.
- Experiment specs: a condition may have its own `seeds` and `per_seed` changes (validated: only for seeds it runs). E007 uses this to give each evolved population its own evaluation world and its own brains.
- The batch runner keeps task statuses as a list of pairs instead of a dict keyed by task: a config holding lists can't be hashed (found by E007's smoke run).
- Golden values for `configs/neural.yaml` (seed 42, 1,000 ticks): Darwin arm64 state and event digests recorded. The event test runs only where confirmed (`NEURAL_EVENTS_CONFIRMED`): unlike the rule-based runs, neural runs depend on `tanh` from the platform's maths library, so cross-platform event agreement is not assumed. Linux x86_64 values are to be recorded in a Linux session.
**Why:** E007's evaluation must run brains evolved elsewhere, reproducibly and identifiably; a file reference would leave the config hash blind to the brains. Per-condition seeds keep one spec (and one batch run, resumable and parallel) for the whole evaluation. Golden values lock E007's code before it runs.
**Alternatives:** a path to a brains file in the config (hash doesn't cover the content); one spec per evaluation world (dozens of files); assuming neural event digests are portable (untested).

## D-044 · Inspecting a decision by replay (2026-10-19)

**Decision:** `genesis inspect RUN_DIR --tick T --organism ID [--weights]` (or `--config FILE --seed S`) replays the run to the start of tick T, lets the simulation take that tick, and prints the organism's decision from the simulation's own record: what it sensed, the 7 inputs, the 6 hidden sums and activations, the 2 outputs and how they became a turn and throttle, and the result (heading, position, energy, whether it ate or died). The simulation keeps the controller's `Thought` in `last_decision` (it already computed it). The replay is checked against the recorded ticks.csv row for that tick, and a run recorded on another OS family or machine is flagged.
**Why:**
- **Replay instead of logging:** recording every decision would be ~1 KB per organism per tick (gigabytes per run); determinism makes any tick recoverable from config and seed.
- **Print the simulation's own computation:** recomputing it separately could drift from the simulation's wiring; reading `last_decision` cannot.
- **Check, don't assume, the replay:** comparing the tick's counts with ticks.csv catches a replay that has diverged (a code change since recording, or another platform, D-027).
**Alternatives:** logging decisions for chosen organisms during the run (needs knowing in advance whom to watch); snapshots every N ticks to replay from (faster for late ticks; unnecessary at ~2,000 ticks/s).

## D-043 · Recording behaviour and brains (run-folder version 4) (2026-10-19)

**Decision:** two new files in every run folder, and matching lake tables. `behaviour.csv`: one row per recorded tick, for every controller: organisms deciding, how many saw food, the share whose applied turn brought seen food closer to straight ahead (`|bearing − turn| < |bearing|`), mean |turn|/max_turn, mean throttle, and with brains the mean per-weight population sd and the mean |weight − founder's weight|. `brains.csv`: one row per organism with a brain, its 62 parameters under readable names (`wh_3_food_ahead`). The simulation keeps the tick's observations and actions as `last_decision` (references, no copies); the recorder reads them. Schema version 4; every earlier file is unchanged. Reports gain a Behaviour section (rolling means; a 0.5 "random turning" reference).
**Why:**
- **Behaviour, not weights, is what matters:** 62 numbers per organism are unreadable; "turns toward food" and "throttle" are what selection acts on, and they are measured identically for the rule-based controllers, which gives E007 its baselines (seeker = 1.0, random walk ≈ 0.5, verified by tests).
- **Applied, not requested, actions:** a rule asking for a sharp turn is credited with the turn its body allowed.
- **Whole brains at birth, not brain mutations:** 62 × births mutation rows would dwarf the gene log; a brain never changes, so one row per organism is complete and exact (values round-trip bit for bit).
- **Separate files:** adding columns to ticks.csv would change its bytes for every run.
**Alternatives:** per-weight statistics in gene_stats (62 extra rows per tick); behaviour averaged over the sampling interval (smoother, but different semantics from the other stock columns).
**Correction to D-042's first observation:** recorded with this measure, the same run (neural.yaml, seed 1) goes from `toward_food` 0.57 at tick 0 to 0.85 at the final tick, not 100%. D-042's figure came from a cruder one-off check (sign of the turn on one tick, ignoring food within 0.1 rad of straight ahead) and is superseded. Throttle 0.55 → 0.78 agrees.

## D-042 · The neural controller in the tick (2026-10-19)

**Decision:** `controller: neural` (requires a `brain:` section). Each tick the simulation adds `BodySenses` to the observations (wall distance ahead, own sense range, max turn and reproduction threshold) and stacks the living organisms' brains; `NeuralController` draws one uniform noise value per organism from the controller stream, builds the inputs (D-040), runs one forward pass (D-039), and returns turn = output₀ × max_turn and throttle = output₁. `think()` returns inputs, every activation and the actions, for inspection. Rule-based controllers get exactly the observations they always did. A `brain:` section with a rule-based controller is allowed: brains are inherited and mutated but never used, a no-selection control for weights. `configs/neural.yaml` is `evolution.yaml` with the neural controller, a brain section, and every expressed gene frozen, so only brains evolve.
**Why:**
- **Turn as a fraction of max_turn:** the brain chooses within what its body allows; mapping to a fixed angle would mostly saturate against the limit and hide the output's value.
- **BodySenses only for neural runs:** rule-based runs do no extra work and stay byte-identical (verified against `main`).
- **Frozen genes in neural.yaml:** a change in behaviour can then only come from the brain, not from speed or sense range evolving alongside it.
- **The carried-but-unused option:** E007 can compare weight changes under selection with drift alone, like the neutral twins of D-025.
**First observation (one seed, anecdotal):** in `neural.yaml` seed 1, the share of food-seeing organisms turning toward food rose from 57% at tick 0 to 100% at tick 20,000; mean throttle from 0.53 to 0.78. Settled population and meals per organism-tick were similar for neural, seeker and random walk, as expected when food supply sets population size (E004), so E007 needs an endpoint that is not pinned by the food supply.
**Alternatives:** passing brains inside `Observations` (brains aren't observations); a controller that stores brains itself (it would hold state that belongs to organisms and go stale at every birth and death).

## D-041 · Brains are inherited like genes, with their own stream (2026-10-19)

**Decision:** an optional `brain:` config section (`weight_limit` 4, `initial_sd` 0.5, `mutation_rate` 0.1 per weight, `mutation_size` 0.2). When present, every founder gets its own brain, weights Normal(0, 0.5) reflected into ±4, drawn in founder order; at each birth every weight mutates with probability 0.1 by a Normal(0, 0.2) step, reflected into ±4. All draws come from a seventh stream, `brain`, appended after `mutation`. Both draws happen for all 62 weights at every birth. `mutation.enabled: false` freezes brains too. Brain changes are not written to `mutations.csv` (whole brains are recorded at birth in 4.5). The state digest includes weights when present. When the section is absent it is omitted from the config dump, so existing config hashes are unchanged.
**Why:**
- **One random brain per founder** (unlike the shared scalar genome): identical founder brains would give selection nothing to act on until mutation built up variation; zero weights would make every founder behave the same.
- **Own stream, appended:** rule-based runs and the scalar-gene mutation draws stay bit-identical; verified by the golden tests, a stream test, and byte-identical recorded runs against `main`.
- **Fixed draws per birth:** one mutation's outcome cannot shift every later one (D-009).
- **Reflection, not clamping:** the gene rule (D-019); clamping would pile weights up on ±4.
- **Sizes are judgment calls:** ±4 bounds every sum (D-039); initial_sd 0.5 gives founders varied but mostly unsaturated hidden units; about 6 of 62 weights change per birth by ~5% of the range. E007's pilot (4.7) may revise them before pre-registration.
**Alternatives:** brain weights as 62 named genes in `Genome` (would flood gene_stats and mutations.csv, and change their schemas); crossover between parents (there is no sexual reproduction); per-weight mutation sizes that themselves evolve (self-adaptation; another layer to explain).

## D-040 · The brain's seven inputs (2026-10-19)

**Decision:** the input vector is, in order: food_seen (0/1), food_ahead = cos(bearing), food_left = sin(bearing), food_closeness = 1 − distance/sense range, energy = energy/reproduction threshold capped at 1, wall_ahead = 1 − (distance to the wall along the heading)/sense range clipped to [0, 1], and noise, uniform in [−1, 1], drawn from the controller stream. Food inputs are 0 when no food is in sight. Built by `intelligence/brain_inputs.py`; rule-based sensing is unchanged.
**Why:**
- **Normalised to [−1, 1], 0 = nothing to report:** no input can drown out the others by scale alone, and every weighted sum stays bounded (D-039).
- **cos and sin, not the angle:** the bearing jumps from +π to −π directly behind; cos/sin change smoothly.
- **A separate food_seen flag:** "no food" and "food exactly sideways" both have cos = 0; the flag tells them apart.
- **Wall sensor:** hard walls (D-004) are the one obstacle in the world; without it a brain could not learn to avoid them. Measured against sense range so "close" means the same for walls and food.
- **Noise:** the baselines wander randomly; a brain without randomness could only go straight or circle, an unfair handicap in E007. Its weights decide how much noise matters.
- **Energy as a fraction of the threshold:** "how close to reproducing", meaningful whatever the threshold gene is.
**Alternatives:** absolute heading and position (meaningless without a map, and would let brains memorise one world); several food targets (more inputs, slower evolution); distance-weighted food "smell" fields (more realistic, harder to inspect).

## D-039 · The organism brain: 7 inputs, 6 hidden, 2 outputs, one way of adding (2026-10-19)

**Decision:** a fixed-topology feedforward network in NumPy: 7 inputs (designed in 4.2), one hidden layer of 6 tanh units, 2 outputs (turn via tanh, throttle via sigmoid), with separate bias vectors: 62 parameters. Parameters are stored as one flat vector in a fixed order (hidden weights row by row, hidden biases, output weights row by row, output biases). Inputs are clipped to [−1, 1]; NaN inputs raise. All weighted sums go through one function, `forward()`, written as multiply-then-`sum` over the last axis.
**Why:**
- **2 outputs, not 3:** eating is automatic whenever food is in reach (D-013), so a "forage" output would decide nothing. Chunk 04A allows this simplification if it is recorded.
- **Small:** 62 parameters is enough to represent "turn toward food, slow down when full" and small enough to inspect by hand and evolve in a few thousand generations.
- **tanh/sigmoid:** bounded and smooth. The sigmoid is computed as 0.5·(1 + tanh(z/2)), the same function in a form that never overflows.
- **Clipping inputs and bounding weights (±4, in 4.3):** keeps every sum finite (at most 7·4 + 4), so outputs are always defined.
- **One summation method:** `@`, `einsum` and multiply-then-`sum` add in different orders. Measured on the development Mac, about a third of values differ in the last bit between methods. One function plus a batch-equals-single test keeps the simulation and the inspector (4.6) bit-identical.
**Alternatives:** a 3-output network with a forage decision and cost (adds a decision without a choice); PyTorch modules (hide the arithmetic; a large dependency); a larger or recurrent network (memory between ticks; harder to inspect and slower to evolve).

## D-038 · Per-tick work on arrays, organisms stay the source of truth (2026-10-19)

**Problem:** at realistic populations (~100 organisms) the profile was not the distance maths but Python: `Organism.spend` was called three times per organism per tick (5.6 million calls in a 20,000-tick evolution run), each cost formula once more, `cause_of_death` and `can_reproduce` once each, and every position was written back one NumPy scalar at a time. The recorder added a quarter again: 24 tiny NumPy reductions per tick for gene statistics, six attribute lookups per organism, and `dataclasses.asdict` (a deep copy) for every tick row and event.
**Decision:** `Simulation.step` builds this tick's arrays once (positions, energies, traits), and from then on works on arrays: `costs.living_costs` gives the three cost arrays, `organism.spend_all` charges them in the same order with the same `min` / subtract / add operations `spend` performs, deaths and reproduction eligibility are array comparisons, and values are written back with `tolist()` (plain Python floats, same values). The `Organism` objects remain the only lasting state: every tick starts by reading them, so tests and future code may still set `org.x` or `org.energy` directly. The recorder reads all six genes with one `attrgetter` per organism into a contiguous (genes × organisms) matrix and reduces it along `axis=1`; `tick_row`, events and `Genome.as_dict` build their dicts without `asdict`.
**What was checked, not assumed:** (1) a (genes, organisms) matrix reduced along its contiguous axis gives exactly the per-gene 1-D results, while an (organisms, genes) matrix reduced along axis 0 does not (NumPy accumulates in a different order; measured, and a test asserts the contiguous layout); (2) `np.power` differs from Python's `**` in the last bit for exponents other than 0 and 1, so the drag factor keeps Python's `**` per organism; (3) the scalar `spend` / cost functions stay as the stated rules, and tests assert the array versions equal them bit for bit on random inputs including organisms that run out of energy mid-payment; (4) golden digests, the fifteen extended scenarios and two recorded run folders are unchanged.
**Why not a full "structure of arrays" redesign** (positions and energies living permanently in arrays): it would make the organism objects stale copies, which tests and the teaching design rely on, for a further gain of perhaps a third. Revisit if a later milestone needs 10,000 organisms.
**Measured:** see docs/benchmarks.md (2026-10-19).

## D-037 · hypothesis for property-based tests (dev only) (2026-10-19)

**Decision:** add `hypothesis` 6.170.1 to the dev dependency group. It generates test inputs from a description ("arrays of up to 40 points with coordinates in [-20, 120]"), runs the test on hundreds of them, and when one fails, shrinks it to the smallest failing example. First used for the spatial grid (D-036), where the bug-prone inputs (points on cell boundaries, duplicates, targets exactly at the reach) are easy to describe and hard to enumerate by hand. Runtime, not test, code gains no dependency.
**Why:** a seeded loop over random inputs only tries what we thought of; hypothesis also tries boundary values, repeats, tiny and huge numbers on purpose, and reports a minimal failing case instead of a 3,000-row array.
**Alternatives:** hand-written seeded random loops (kept too, for the large sizes hypothesis is slow at); pytest parametrization alone (misses what nobody wrote down).
**Rule of use:** `deadline=None` (NumPy timing varies) and an explicit `max_examples`; a hypothesis test must never depend on the simulation's own random streams.

## D-036 · Spatial grid for sensing and feeding, bit-identical to all-pairs (2026-10-19)

**Problem:** sensing and feeding each computed every organism-to-food distance (n × m) per tick. Profiling (docs/benchmarks.md, 2026-10-19) measured them at 66–72% of a tick at 1,000–3,000 organisms, as D-017 anticipated. At the default population (~100) they were ~17%.
**Decision:** `core/spatial.py` cuts the world into square cells with side = the longest reach, and compares each organism only with food in its own cell and the ring around it (`pairs_within_reach`, `nearest_within_reach`). The grid only *proposes candidates*, a guaranteed superset of the true pairs (reach padded by a few units in the last place before cell bounds are computed); each candidate's distance is then computed with the same `np.hypot` on the same offsets as before, and the same `<=` test applied. Below 4,096 organism × food pairs, or when the grid would still check more than half of all pairs, the original all-pairs code runs. Sensing keeps "lowest index wins ties" via a stable sort by distance over pairs already ordered by (organism, food); feeding gets its in-reach pairs in the same (organism, food) order as `np.nonzero` gave, so the tiebreak stream's draws land on the same pairs.
**Evidence it changes nothing:** `tests/test_regression.py` golden digests (Linux state digests included) pass unchanged; fifteen further scenarios (both configs and controllers, 20,000-tick evolution runs, 1,000 and 3,000 organisms, zero food, the population cap, genes at their bounds, an odd-shaped world, a maximum age) gave identical state, event and energy digests before and after, and two full recorded run folders were byte-identical. Measured first: on this machine NumPy's `hypot` and `arctan2` give the same bits for the same inputs whether computed on a whole (n, m) matrix, a slice, a strided view or a fancy-indexed subset (200,000 values, 0 mismatches). `math.hypot` and `np.power` with exponents other than 0 and 1 do *not* match their NumPy/Python counterparts, so they are never substituted.
**Measured:** benchmark N = 1000: 41 → ~110 ticks/s; N = 3000: 9 → ~30 ticks/s (before the other changes in the same PR). Evolution-config runs barely change: there the Python loops dominate (see docs/benchmarks.md).
**Alternatives:** `scipy.spatial.cKDTree` (`sparse_distance_matrix` gives candidate pairs, but its own distance arithmetic would have to be padded and re-tested; the grid is pure NumPy and its superset argument is one paragraph); smaller cells (fewer candidates, more cells to look up: no gain measured); keeping D-017 (fine at 100 organisms, 3× slower at 1,000+).
**Revisit if:** sense ranges routinely approach the world size (the grid declines and all-pairs runs), or a platform shows `hypot` results that depend on array position (the test suite would catch it: `tests/core/test_spatial.py`).

## D-035 · An executed, output-free notebook (2026-10-19)

**Decision:** one Jupyter notebook demonstrating the full workflow on a small demo experiment, built with nbformat, executed by the test suite with nbclient, committed without outputs (a test enforces it). New dev-only dependencies: ipykernel 7.4.0, nbclient 0.11.0, nbformat 5.11.1.
**Why:** notebooks rot when not re-run; executing them in tests catches that. Saved outputs make noisy diffs and can contradict the code; output-free commits avoid both. A demo experiment keeps it fast (~6 s) and keeps real data untouched.
**Alternatives:** nbstripout as a git filter (strips automatically, but must be installed per clone); papermill (parameter injection, not needed); marimo (plain-Python notebooks, not chosen in the Milestone 3 plan).

## D-034 · Self-describing, verifiable exports (2026-10-19)

**Decision:** exports carry their own documentation (README cut from the data dictionary) and a manifest with row counts and SHA-256 checksums; Parquet by default, CSV on request; rows sorted by primary key.
**Why:** "reloadable and independently analysable" needs more than files: a reader without Genesis Lab must know what each column means and be able to prove the files are complete and unchanged. Cutting the README from the dictionary means it can't drift.
**Evidence:** a pure pandas/NumPy/SciPy script (no Genesis Lab import) reproduced E003's H7a from the export: median interaction +5.12, 14/6, sign p 0.115, permutation p 0.0082 vs published 0.0077 (different random samples of 20,000 sign patterns; difference within one standard error).
**Alternatives:** a DuckDB database file (one file, but needs DuckDB to read); CSV only (universal, ~10× larger, loses types).

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
**Revisited 2026-10-19:** the spatial index was added as a grid (D-036), together with array-based per-tick work (D-038), after a stress-test pass measured both; results are bit-identical.

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
