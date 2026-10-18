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

## Upcoming (Milestone 1)
- Vectorized distance calculations (1.4)
- Pure functions and separation of concerns (1.4)
- Pseudo-random number generators, seeds, and reproducibility (1.5)
- Simultaneous update and conflict resolution; invariants and conservation checks (1.6)
- Population dynamics and carrying capacity (1.7)
- CLI design; CSV output (1.8)
- Profiling and benchmarking (1.9)
