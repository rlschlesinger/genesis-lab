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

## Upcoming (Milestone 1)
- Data validation with Pydantic; YAML configuration (1.1)
- NumPy arrays and vectorized distance calculations (1.2–1.4)
- Dataclasses and object-oriented state (1.3)
- Pure functions and separation of concerns (1.4)
- Pseudo-random number generators, seeds, and reproducibility (1.5)
- Simultaneous update and conflict resolution; invariants and conservation checks (1.6)
- Population dynamics and carrying capacity (1.7)
- CLI design; CSV output (1.8)
- Profiling and benchmarking (1.9)
