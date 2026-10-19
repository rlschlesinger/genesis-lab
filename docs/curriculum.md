# Curriculum

What has been covered, where it appears in the code, and what comes next.

## Covered

### 1.0 · Project scaffold
- **Virtual environments:** why each project gets its own isolated Python (`.venv/`).
- **Dependency pinning:** `pyproject.toml` states *acceptable* versions; `uv.lock` records the *exact* versions installed. Committing the lock is what makes the environment reproducible.
- **src layout:** code lives in `src/genesis/`, so tests import the *installed* package, the same way a user would. This catches packaging mistakes early.
- **Dependency groups:** `pytest` and `ruff` are dev-only and are not needed to run a simulation.
- **Linting vs formatting:** `ruff check` finds likely bugs and style problems; `ruff format` rewrites layout consistently.
- **Tests:** pytest discovers `test_*.py` files and runs every `test_*` function.

### 1.1 · Configuration (`src/genesis/core/config.py`)
- **Validate at the boundary:** untrusted input (a file) becomes a trusted typed object exactly once.
- **Pydantic models:** fields with types and constraints (`Field(gt=0)`), `Literal` for fixed choices, `X | None` for optional values.
- **Field vs model validators:** single-field rules vs rules that relate several fields (`@model_validator`).
- **`extra="forbid"` and `frozen=True`:** typos become errors; configs can't change mid-run.
- **`yaml.safe_load`:** parses data only, never executes code embedded in the file.
- **Units:** every number states its unit (world units, ticks, EU, radians).
- **pytest techniques:** fixtures (`raw`), `parametrize` (one test, many cases), `pytest.raises(..., match=...)`, `tmp_path`.

### 1.2 · World and food (`src/genesis/core/world.py`, `resources.py`)
- **NumPy arrays:** shape `(n, 2)`, dtype `float64`, column slicing (`positions[:, 0]` = all x values).
- **Vectorization:** one call operates on every row (`rng.uniform(..., size=(k, 2))`, `np.clip`).
- **Broadcasting:** a length-2 array `[width, height]` applies per column to an `(n, 2)` array.
- **Boolean masks:** `keep[idx] = False; positions[keep]` removes rows in one step.
- **Views and read-only flags:** sharing data without copying, while preventing mutation.
- **Poisson distribution:** random counts of independent events at a fixed average rate; sample noise shrinks as √(rate / n).
- **Dependency injection of randomness:** functions receive a `Generator` instead of creating one.
- **Testing randomness:** seeded statistical tests with tolerances derived from the standard error.

### 1.3 · Organisms (`src/genesis/core/organism.py`)
- **Ticks:** discrete simulated time. One tick = one full pass of the update sequence; it has no fixed real-world duration.
- **Dataclasses:** `@dataclass` generates `__init__`, `__repr__`, `__eq__`; `frozen`, `slots`, `kw_only` add safety.
- **Enums:** `StrEnum` for a fixed set of named values that serialize as strings.
- **Queries vs commands:** `cause_of_death` only reports; `die` changes state. Separating them enables simultaneous updates.
- **Invariants and fail-fast:** dead organisms raise on any action; energy never goes negative.
- **Floating-point arithmetic:** 0.35 isn't exact in binary; compare floats with a tolerance (`pytest.approx`).
- **Zero- vs one-based counting:** the 143rd tick is tick 142.

### 1.4 · Sensing, controllers, movement (`intelligence/`, `core/movement.py`, `core/geometry.py`)
- **Radians and trigonometry:** `cos`/`sin` turn a heading into x/y steps; `atan2` turns an offset back into an angle.
- **Angle wrapping:** one canonical value per direction, in `[-pi, pi)`.
- **Broadcasting in 3D:** `(n, 1, 2) - (1, m, 2) -> (n, m, 2)`, giving every pairwise offset in one step.
- **`argmin` and fancy indexing:** `distances[rows, nearest]` picks one column per row.
- **Pure functions:** controllers read inputs and return outputs, with no side effects, so they're easy to test and to swap out.
- **Protocols:** an interface defined by method shape, not inheritance.
- **Requests vs limits:** the controller asks, the body (traits) decides.
- **Control conditions:** baselines differ in exactly one behaviour, so outcome differences are attributable.
- **Debugging a failing test:** trace the behaviour, then decide whether the code or the test is wrong. Here it was the test (checking the final position, not the closest approach).
- **Turning circles:** a speed / turn-rate limit creates a minimum radius; a full-speed organism can't stop on a target.

### 1.5 · Simulation loop (`src/genesis/core/simulation.py`)
- **Pseudo-random number generators:** a deterministic formula that produces a random-looking sequence from a seed.
- **Independent streams:** `SeedSequence.spawn` gives one generator per subsystem, so a draw in one never shifts another. (Analogy: separate decks of cards instead of one shared deck.)
- **Orchestration:** one object owns the state and runs the steps in a fixed order; the parts it calls stay simple.
- **Snapshots:** copy state into arrays once at the start of the tick, so every organism sees the same world.
- **Hashing:** SHA-256 turns the whole state into a short fingerprint; any change, however tiny, changes it completely.
- **Determinism checks:** the same digest in two separate processes is stronger evidence than two runs in one process.
- **Reviewing your own tests:** an assertion that compares a value with itself can never fail. Check that a test can fail.

### 1.6 · Eating and the energy ledger (`core/feeding.py`, `core/energy.py`)
- **Conflict resolution:** sort candidate pairs, then greedily accept those whose sides are both still free.
- **`np.nonzero`:** the (row, column) of every True entry, here the in-reach pairs.
- **`np.lexsort`:** sorting by several keys (distance, then a random tie-breaker).
- **Fairness testing:** over 400 seeds, each side of an exact tie wins about half the time; an ID-based rule would win all 400.
- **Conservation accounting:** stocks, inflows, outflows and transfers, like a bank balance; check it every tick.
- **Floating-point tolerance:** `math.isclose` with relative and absolute tolerances; `math.fsum` for accurate sums.
- **Mutation testing by hand:** plant a bug and confirm the safety net catches it.
- **Feedback loops:** consumption changes how much food can spawn, so inflow depends on behaviour.

### 1.7 · Reproduction (`evolution/reproduction.py`)
- **Hidden selection pressure:** any rule that systematically favours some organisms (e.g. by ID) acts like selection. Use neutral randomness unless the bias is the thing being studied.
- **Sampling without replacement:** `rng.choice(..., replace=False)`.
- **Uniform points in a disc:** radius = R·√u, not R·u, because area grows with the square of the radius.
- **Event timing:** when something is created mid-tick, define exactly when it first acts, and test it.
- **Carrying capacity:** a population grows until it uses up the energy that comes in. Back-of-envelope: (spawn rate × energy per item) ÷ cost per organism per tick = 2 × 20 ÷ 0.35 ≈ 114. Observed ~112–116 (seed 42).
- **Choosing metrics:** two controllers can reach the same population for different reasons; population size alone would hide the difference.

### 1.8 · Metrics, CLI, output files (`analytics/`, `cli.py`)
- **Provenance:** seed, config, git commit, dirty flag and versions make a result traceable. "Dirty" means the commit doesn't fully describe the code.
- **CSV:** tables as text; `csv.DictWriter`; `lineterminator="\n"` for identical bytes on every OS.
- **JSON:** nested metadata; `json.dumps(indent=2)`.
- **Atomic writes:** write a temp file, then `os.replace`, so a crash can't leave half a file.
- **Status records:** write "running" first, so failures leave evidence.
- **argparse:** subcommands, options, defaults, `--help` for free; exit codes 0/1/2.
- **Entry points:** `[project.scripts]` turns a Python function into a terminal command.
- **Thin interfaces:** the CLI only translates arguments; the logic stays reusable.
- **Test doubles:** `monkeypatch` replaces a method to simulate a failure.
- **Genetic drift:** with identical organisms, 22 of 30 founder lineages died out by chance in 5000 ticks (seed 42).

### 1.9 · Benchmarking and the first controlled experiment
- **Benchmarking:** time repeated runs, report the best, and normalize (µs per organism-tick) so sizes can be compared.
- **Profiling:** `cProfile` shows where time actually goes (here: n × m distance tables, ~75% at N = 1000). Measure before optimizing, and only optimize when it matters.

### 3.12 · Stress test and optimization without changing a result (2026-10-19)
- **Profile at the sizes you actually run:** at 1,000+ organisms the distance tables dominated (as D-017 predicted); at the ~100 organisms every experiment used, Python call overhead did (three `spend()` calls per organism per tick), and the recorder cost a quarter again. The two fixes are different (D-036, D-038).
- **Spatial grid:** cut the world into cells no smaller than the longest reach; anything within reach lies in your cell or the ring around it. The grid only *proposes candidates*; the exact test still decides. That is what makes it a pure speed-up.
- **Bit-identical means the same operations on the same numbers:** `hypot` on a subset of pairs gives the same bits as on the whole table (measured: 200,000 values, 0 mismatches), but `math.hypot` vs `np.hypot`, `np.power` vs Python `**`, and summing a matrix along a non-contiguous axis do *not*. Check such assumptions with a script before relying on them, then lock them in with tests.
- **Vectorizing a loop:** `min`, subtract and add on arrays are the same IEEE operations as on scalars, in the same order per element, so `spend_all` equals `spend` in a loop. Keep the scalar rule as the stated reference and test the array version against it.
- **Property-based testing (hypothesis, D-037):** describe the inputs, let the library search for a counter-example, get back the smallest one. Good for "two implementations must agree" on awkward inputs (cell boundaries, duplicates, exact reach).
- **Golden values beyond the test suite:** before touching anything, record digests for every scenario you can think of (both configs, both controllers, long runs, big populations, edge cases, full run folders) and compare after each change. The regression test covers one; the stress pass covered fifteen plus two folders.
- **Stress testing is about finding what breaks, not proving nothing does:** list the edges (empty population on tick 0, the cap, zero food, genes at their bounds, 50,000 ticks, 120-run batches, ingest and SQL at that scale, memory), run them, and turn anything surprising into a test.
- **Pre-registration:** write question, hypotheses, metrics and analysis *before* running, and commit them, so the history proves the order.
- **Paired design:** the same seeds for both conditions; analyse per-seed differences.
- **Sign counting:** 10 of 10 pairs in one direction has chance probability ≈ 0.002 if there is no real difference.
- **Confirmatory vs exploratory:** results that test a stated hypothesis vs patterns noticed afterwards (which become new hypotheses).
- **Separating fact from explanation:** "cost per tick differs" was measured; "because of walls" is a likely, untested reason.
- **Censoring:** organisms still alive at the end have unknown lifespans; excluding them biases lifespan downward.

## Milestone 1 complete

## Milestone 2: Genetics and evolution

### 2.0 · Golden tests (`tests/test_regression.py`)
- **Characterization tests:** record what the code *does* (a state digest) to catch accidental behaviour changes during refactors.
- **Refactor vs behaviour change:** a refactor keeps every result identical; anything else must be a deliberate, logged decision.
- **Floating-point is not portable:** `hypot` and `arctan2` can differ in the last bit between CPUs and operating systems, so a bit-for-bit digest is a per-platform value. Hashing only integer counts (who was born, who died, what was eaten) gives a check that holds everywhere (D-027).

### 2.1 · Genome (`evolution/genome.py`)
- **Genotype vs phenotype:** the inherited information vs the expressed characteristics. `express()` is the mapping.
- **Unexpressed genes:** the neutral marker is inherited but has no effect, so nothing can select for it. Its changes are pure drift.
- **Bounds:** every value a gene could ever reach must be physically valid, not just its starting value.
- **Circular imports:** `typing.TYPE_CHECKING` lets two modules mention each other's types without importing each other at runtime.
- **Single source of truth:** one gene list, plus a test that the three places naming genes agree.

### 2.2 · Mutation (`evolution/mutation.py`)
- **Bernoulli trial:** an event that happens with probability p; here, "does this gene mutate?".
- **Normal distribution:** mean (centre) and standard deviation (typical size); about 68% of draws fall within ±1 sd.
- **Unbiased mutation:** a mean-zero step means mutation itself has no preferred direction.
- **Boundary artefacts:** clamping creates pile-ups that mimic selection; reflection doesn't. Always ask whether a pattern could come from the rules themselves.
- **Drift saturates:** a neutral gene's spread grows (≈ step × √generations at first), then levels off at the uniform distribution's sd, (max − min)/√12 ≈ 0.289 for a 0–1 range.
- **Frozen genes as experimental control:** letting only one gene vary isolates its effect.
- **Testing randomness:** check rates and spreads against their expected values, with tolerances from the standard error.

### 2.3 · Inheritance (`core/simulation.py` step 7, `mutations.csv`)
- **Heredity:** children carry their parent's genome, with occasional mutations.
- **Event logs:** recording every change makes every genome reconstructable, and makes the integrity test possible.
- **Invariant tests over whole runs:** check a property (genome = parent + logged changes) for *every* organism, not a sample.
- **Updating golden tests responsibly:** prove behaviour is unchanged under the old definition before changing the definition.
- **Fingerprints need complete state:** leaving out anything that can differ (like an unexpressed gene) makes "identical" claims unreliable.
- **Selective sweeps and hitchhiking:** when one family takes over, every gene it carries rises with it, neutral ones included (seed-42 demo: neutral marker sd only 0.031).
- **Observation vs adaptation:** directional change in one unreplicated run, without trade-offs or a drift comparison, isn't evidence of adaptation.

### 2.4 · Trade-offs (`core/costs.py`, `configs/evolution.yaml`)
- **Trade-offs create optima:** a benefit with a rising cost has a best value; a free benefit just runs to its limit.
- **Nonlinear costs:** with drag, cost per tick grows with speed squared, so doubling speed quadruples the cost.
- **Relative costs:** scaling drag by speed ÷ founder speed leaves founders' costs unchanged.
- **Positive controls:** keep one known free lunch to prove selection can be detected at all.
- **Spotting hidden free lunches:** max_turn had no cost, so it was frozen rather than left as a confound.
- **Config copies with a guard test:** a test lists exactly which settings may differ.
- **Fresh seeds:** don't test a hypothesis on the data that suggested it.

### 2.5 · Trait statistics (`analytics/recorder.py`)
- **Describing distributions:** mean (centre), standard deviation (spread), min/max (extremes).
- **Population vs sample sd:** divide by n to describe exactly these organisms; divide by n − 1 to estimate a larger group's spread.
- **Tidy (long) data:** one observation per row; variable names as values, not column names.
- **Sampling for storage:** summaries every tick, full detail at intervals.
- **Recount tests:** derived statistics must be reproducible from the raw data they summarize.
- **Observer pattern:** the recorder watches the simulation and never changes it (a test proves the digest is unaffected).
- **Time series reveal timing:** the positive control's drop happened between ticks 1000 and 5000; a final value can't show when selection acted.
- **Check estimates against measurements:** "a few MB" was really 16 MB.

### 2.6 · Reports (`report/`, Plotly)
- **Visualizing distributions over time:** mean ± sd bands for trends; heatmaps for whole distributions (shifts, narrowing, splits).
- **Honest axes:** each gene's y-axis spans its full allowed range, so changes aren't exaggerated by zooming in.
- **Downsampling for display:** a fixed stride keeps plots light; the raw data stays complete.
- **Deterministic output:** fixed element IDs make generated HTML byte-identical.
- **Design tokens:** one palette shared by CSS and charts, so they can't drift apart.
- **Verify by looking:** a screenshot caught overlapping subplot titles that no test did.
- **Precise tests:** "no font URL anywhere" failed on Plotly's own library code; the right check is our markup.
- **A sanity check from theory:** the mean absolute mutation step should be size × √(2/π) ≈ 0.040; four genes matched. Metabolic rate (0.034) was lower because steps reflected at its lower bound.

### 2.7 · Significance tests (`analytics/significance.py`)
- **Null hypothesis and p-value:** assume "no difference", then ask how surprising the data would be. A p-value is not the probability that a hypothesis is true.
- **Binomial distribution:** the number of heads in n fair flips; the sign test counts the ways to be at least as lopsided (`math.comb`).
- **Permutation tests:** build chance's distribution by re-labelling the data many times; exact when every arrangement can be listed.
- **Sampling with a seed:** large tests sample arrangements reproducibly; the "+1" correction avoids p = 0.
- **Calibration:** when nothing is going on, a valid test raises false alarms at its stated rate (~5%).
- **Statistical power:** how often a test detects a real effect (~70%+ for a 1-sd effect with 10 pairs).
- **Multiple comparisons:** five tests at 5% give a ~23% chance of at least one false alarm; Holm's correction controls it.
- **Effect size vs significance:** E001's capacity difference is significant yet only 3.7%.
- **Resolution floor:** 10 pairs can't give p below 0.002; more evidence needs more replicates.

### 2.8a · Designing the experiments (`docs/experiments/E002`, `E003`)
- **Null models must match the question:** a neutral marker can't be the drift baseline for genes that start elsewhere in their ranges. A neutral twin of each gene can.
- **Positive control:** test the method on an effect known to exist (free metabolism) before trusting it on unknowns.
- **Factorial (2 × 2) designs and interactions:** "does scarcity change selection?" is a difference of differences, not a single comparison.
- **Blind feasibility pilots:** check that runs survive using separate seeds, looking only at population and extinction.
- **Pre-registration with review:** commit definitions, scripts and seeds before any run; a reviewer can then check them.
- **Smoke tests:** run the full pipeline on throwaway inputs to test the code without peeking at results.
- **Predicting null results honestly:** a floor effect (metabolic rate near 0.02) can hide real effects; a non-significant result isn't evidence of no effect.

### 2.8b · Running the experiments
- **When a run fails mid-experiment:** reproduce, find the root cause, fix, record a protocol deviation *before* any results, and re-run everything from one commit.
- **Floating-point accumulation:** adding small numbers one by one to a huge total loses precision; sum exactly per batch (`math.fsum`) and scale tolerances to what has flowed through.
- **Positive control success:** the method detected the known effect in 20/20 seeds, so the other results can be trusted to mean something.
- **Tests that disagree:** permutation (uses sizes) vs sign (direction only); report both, decide by the one pre-registered.
- **Replication:** E003's control arm reproduced E002 on new seeds, the strongest kind of evidence available here.
- **Correcting yourself in writing:** earlier claims about drift were wrong in size; the record says so.


## Milestone 2 complete

## Milestone 3: The Science Lab

### 3.0 · Schema design (`docs/schema.md`, `docs/data-dictionary.md`)
- **Tables, schemas, primary and composite keys, foreign keys, views.**
- **Why every key includes `run_id`,** and the fan-out bug when a JOIN forgets it.
- **Self-referencing tables** (organisms → parent) and recursive queries.
- **Source of truth vs derived data:** Parquet files are the record; the database is a rebuildable lens.
- **NULL vs NaN:** SQL aggregates skip NULL; a NaN poisons the result.
- **Data dictionaries:** every column's type, unit and when it may be empty.

### 3.1 · Sampling, events and run metadata
- **Stocks vs flows:** a snapshot quantity can be sampled; an "amount during" quantity must be summed over the interval, or totals go wrong.
- **Event logs:** one row per thing that happened, for questions totals can't answer.
- **Canonical hashing:** sorting keys before hashing makes identical settings give identical fingerprints.
- **Format versioning:** a version number in each record lets old and new data be read correctly together.

### 3.2 · ETL into a Parquet lake (`src/genesis/lake/`)
- **Extract, transform, load:** read raw records, convert them to a fixed schema, check, then write.
- **Schemas as code:** the data dictionary becomes Arrow schemas, so writer and checker can't disagree.
- **Stated vs inferred types:** declare every column's type; never let a reader guess.
- **Validation before loading:** primary keys, foreign keys, row counts, ranges, types; refuse the whole record on any failure.
- **All-or-nothing writes:** stage every file, then rename them into place.
- **Columnar storage and compression:** Parquet stored this data ~9.5× smaller than CSV.
- **Damage testing:** break copies of real data in specific ways, and confirm each is caught with the right reason.
- **Format limits show up as test failures:** Parquet's smallest timestamp unit is ms; the schema test caught the silent widening.

### 3.3 · SQL with DuckDB (`lake/db.py`, `docs/sql-examples.md`)
- **SELECT, WHERE, GROUP BY, ORDER BY, LIMIT:** choose columns, filter rows, collapse groups, sort, cap.
- **JOIN ... ON:** match rows across tables; with composite keys, every key column must be in `ON` (fan-out: 1,254 vs 205,788 rows).
- **Views and table macros:** saved queries, with or without parameters.
- **Window functions:** `lag`, rolling `avg ... OVER (... ROWS BETWEEN ...)`, `row_number() ... QUALIFY` for the top row per group; unlike `GROUP BY`, rows aren't collapsed.
- **WITH RECURSIVE:** follow parent pointers back to a founder.
- **JSON in SQL:** `config ->> '$.food.regrowth_per_tick'`.
- **NULL in aggregates:** `count(mean)` counts non-NULL values; `count(*)` counts rows.
- **Testing queries:** compare with an independent computation; break the code on purpose to check the test can fail.
- **Test isolation:** "passes alone, fails in the suite" means tests share state (here: a shared temporary folder).

### 3.4 · Batch experiments (`analytics/spec.py`, `analytics/batch.py`)
- **Configuration as data:** an experiment is a file (conditions × seeds), not a script.
- **Validate everything up front:** build every run's config before running any.
- **Processes vs threads:** CPU-bound Python needs processes (the GIL); tasks must be serializable plain data.
- **Embarrassingly parallel work:** independent runs give identical results in any order (byte-identical test), ~7× faster here.
- **Idempotent, resumable jobs:** skip what's done; detect "done, but with different settings" and refuse to mix.
- **YAML features:** anchors and merge keys (`&neutral`, `<<: *neutral`); quoting `"off"`, which YAML would otherwise read as `false`.
- **Refactoring safely:** after moving conditions into spec files, re-analysing the saved data reproduced every published number.

### 3.5 · Analysis with pandas and SciPy (`analytics/analysis.py`)
- **DataFrames:** query results as tables; `groupby`, `pivot` (long → wide), `loc`.
- **pandas 3 changes:** copy-on-write (chained assignment silently does nothing; use `.loc`); a dedicated string dtype for text.
- **Descriptive statistics:** mean vs median, sample sd (n − 1) vs population sd (n), standard error, quartiles.
- **Confidence intervals:** the percentile bootstrap (resample runs with replacement); the Wilson interval for proportions, and why the textbook interval fails near 0% and 100%.
- **Coverage:** a "95%" interval should contain the truth in about 95% of repeated experiments; check it by simulation.
- **Effect sizes:** raw difference, % of control, Cohen's d.
- **Statistical vs practical significance:** compare the interval with a smallest effect of interest stated in advance.
- **Independent implementations:** two codebases agreeing to 12 decimals is strong evidence both are right; where they differ, find out why (two definitions of "two-sided").

### 3.6 · Experiment dashboards (`report/dashboard*.py`)
- **Show the data, then the summary:** every replicate visible (faint lines, dots) beside the aggregate (bold median, CI).
- **Spread vs precision:** a middle-50% band shows how runs differ; a confidence interval shows how well the median is known.
- **Survivorship bias:** summaries over time only include runs still alive; show how many.
- **Paired difference plots:** one dot per seed against a zero line shows consistency directly.
- **Refactoring with a byte-for-byte check:** shared helpers moved, and the run report stayed identical (compared via `git stash`).
- **Check every screen size:** a layout fine on desktop broke on a phone.

### 3.7 · Exporting data (`lake/export.py`)
- **Self-describing data:** ship the column documentation with the files.
- **Checksums (SHA-256):** prove files arrived complete and unchanged; one extra byte is detected.
- **Manifests:** what was exported, from which code version, how many rows.
- **Reproducing from an export alone:** the real test of independence is re-analysis with no project code.
- **Sampling noise in p-values:** two samplers of 20,000 patterns gave 0.0077 and 0.0082; the standard error of a sampled p is about √(p(1−p)/n) ≈ 0.0006.

### 3.8 · The analysis notebook (`notebooks/analysis-workflow.ipynb`)
- **Notebooks as narrative:** explanation and code interleaved, run top to bottom.
- **Kernels:** the notebook runs in this project's Python (ipykernel, `.venv`).
- **Executable documentation:** tests run the notebook, so it can't silently break.
- **Outputs out of version control:** commit code, not results; results are regenerated.
- **Resolution floor again:** with 6 pairs, p can't go below 2/64 ≈ 0.031, however big the effect (d_z = −7.6 here).
- **Floating-point residue:** 0 computed as a difference of nearly equal numbers can come out as 2.8e-17; make exact cases exact.

### 3.9 · SQL exercises (`docs/sql-exercises.md`)
- **Ten questions about E001–E003:** filters, aggregates, `FILTER`, joins on composite keys, final-tick joins, `lag` windows, `QUALIFY`, `WITH RECURSIVE`, `LEFT JOIN` counting, JSON-derived parameters.
- **Unit of analysis in SQL:** summarize per run first (a `WITH` sub-query), then compare runs.
- **Maximums describe spread, not centre:** drift-only conditions had the highest single seeds despite lower medians.
- **Mutation rate vs selection:** 7 metabolic mutations in 76 births matches the 10% rate; selection changes which lines survive, not how often mutations happen.
- **Documents that test themselves:** printed results are re-checked against the data; a one-digit change is caught.

### 3.10a · Designing Experiments A–C (`docs/experiments/E004–E006`)
- **Dose-response designs:** several levels of the variable, and a model for how the outcome should follow (elasticity: slope of log outcome on log dose; 1 = proportional).
- **Equivalence testing:** "proportional within ±10%" is supported only if the whole interval lies inside the bounds.
- **Mutation–drift balance:** mutation adds variation, drift removes it; their balance rises with the mutation rate.
- **Binary outcomes:** proportions, Wilson intervals, and a trend test across ordered groups (Cochran–Armitage, by permutation).
- **Calibration pilots that look at the outcome:** sometimes necessary; disclose them fully and use separate seeds.
- **Floor and ceiling effects:** an outcome at 0% or 100% can't show differences; pilots find the informative middle.
- **Testing the analysis before the data:** synthetic data with known answers (exponent 0.5, a trend, pure noise).
- **Mistakes in your own queries:** `count(*)` after a join counts joined rows, not runs (the fan-out, made by me in a pilot query).

### 3.10b · Results of Experiments A–C
- **Equivalence supported:** E004's elasticity CI [0.982, 1.001] sits inside ±10%: proportional.
- **Theory confirmed in a simulation:** E005's neutral diversity rises with mutation rate, roughly as √(rate), as mutation–drift balance predicts.
- **A failed prediction is a result:** E006's monotonic founder effect wasn't there; the data suggest a U-shape instead, recorded as a new hypothesis, not a finding.
- **Wide intervals with binary outcomes:** even 50 runs per level leaves ±0.13 on a proportion; differences between levels need many runs.

## Milestone 3 complete

## Milestone 4: Evolving neural brains

### 4.1 · The forward pass (`intelligence/neural.py`, [neural-networks.md](neural-networks.md))
- **Vectors and matrices:** a sense vector in, a weight matrix per layer; row *k* of a matrix holds unit *k*'s weights.
- **Weighted sum and bias:** `z = W·x + b`, worked by hand for a 2-2-2 network.
- **Activation functions:** tanh for signed outputs (turn), sigmoid for fractions (throttle); why bounded functions keep outputs defined.
- **Parameter counting:** 6×7 + 6 + 2×6 + 2 = 62 numbers describe one brain; the flat vector is the genome.
- **Broadcasting a batch:** `(n, h, i)` weights times `(n, 1, i)` inputs, summed over the last axis, runs every organism's brain at once.
- **Floating-point order matters:** `@`, `einsum` and `sum` disagree in the last bit; one code path keeps results bit-identical.
- **Selection vs backpropagation:** no gradient, no right answers; variation plus differential reproduction.

### 4.2 · The sensor vector (`intelligence/brain_inputs.py`)
- **Feature design:** a network can only react to what it is told; choosing inputs matters as much as the network.
- **Normalisation:** every input scaled to [−1, 1] with 0 meaning "nothing", so no input dominates by scale alone.
- **Encoding angles:** (cos, sin) instead of an angle that jumps at ±π.
- **Ray casting:** distance to the first wall along a heading, from one division per wall.
- **Property-based testing found a real edge case:** a heading whose sine is ~10⁻³⁰⁸ overflows the division; the answer (infinity) was right, the warning was not.

### 4.3 · Brains as inherited genes (`evolution/brain.py`)
- **Genotype → controller:** 62 numbers inherited at birth fully determine how an organism will react to anything it senses.
- **Standing variation:** founders start with different random brains, so selection can act from the first generation.
- **Mutation in many dimensions:** each weight mutates independently; on average 6 of 62 change per birth.
- **Append-only random streams, tested:** a seventh stream leaves the first six untouched; brains carried along but unused change nothing else.
- **Backward compatibility:** an optional config section is left out of the saved config when absent, so old runs keep their fingerprints.

### 4.4 · Neural organisms (`NeuralController`, `configs/neural.yaml`)
- **Genotype → behaviour, end to end:** sense → 7 inputs → forward pass → turn and throttle → movement.
- **Scaling outputs to the body:** turn is a fraction of the organism's own max_turn.
- **Evolution found a behaviour nobody wrote:** in one run, turning toward seen food went from 57% (chance-like) to 100%, and throttle rose.
- **Choosing an endpoint:** when food supply sets population size, population and meal rate can't distinguish good foragers from poor ones; E007 must measure something else.
- **Exact replay:** recomputing a tick's decision outside the simulation gives the same bits, the basis for the inspector.

### 4.5 · Recording behaviour and brains (`analytics/behaviour.py`, schema v4)
- **Measure the phenotype that matters:** 62 weights are unreadable; "does it turn toward food?" is what selection sees.
- **Baselines measured the same way:** the seeker scores 1.0, the random walker about 0.5, so neural runs can be placed between them.
- **Wide vs long tables:** one row per brain with 62 named columns (a vector genome) vs one row per (tick, gene) for gene_stats.
- **Schema evolution without breaking old data:** new files, a version number, older runs load with the new tables absent.
- **Smoothing a noisy signal honestly:** a rolling mean, labelled as such, with missing values skipped rather than treated as zero.

### 4.6 · Inspecting a decision (`genesis inspect`)
- **Replay as a debugger:** determinism means any moment of any run can be recreated from config and seed, so nothing per-decision needs storing.
- **Reading a network's computation:** inputs → weighted sums → tanh → outputs → turn and throttle, for one real organism.
- **Reading weights:** which inputs each hidden unit listens to, and how each hidden unit pushes the outputs.
- **Trust but verify:** the replay checks itself against the recording and flags another platform.

## Future learning objectives
- **Milestone 4:** neural networks from scratch in NumPy (forward pass, activation functions), neuroevolution; later PyTorch.
- **Milestone 5:** HTTP APIs with FastAPI, WebSockets, TypeScript, React, rendering with PixiJS.
