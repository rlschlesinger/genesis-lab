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


## Future learning objectives
- **Milestone 2:** mutation and heredity, variation vs selection vs drift, lineage trees, trait distributions.
- **Milestone 3:** pandas, SQL with DuckDB, Parquet, significance tests and effect sizes with SciPy, batch experiment design.
- **Milestone 4:** neural networks from scratch in NumPy (forward pass, activation functions), neuroevolution; later PyTorch.
- **Milestone 5:** HTTP APIs with FastAPI, WebSockets, TypeScript, React, rendering with PixiJS.
