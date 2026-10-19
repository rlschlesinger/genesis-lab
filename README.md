# Genesis Lab

A local-first artificial life laboratory. Digital organisms live in a simulated 2D world, eat, reproduce and (from Milestone 2) evolve. Everything runs on your machine: no cloud services, no API keys.

**Status:** Milestone 1 (The Petri Dish) complete: a running, deterministic ecosystem with recorded results and a first controlled experiment ([E001](docs/experiments/E001-controller-comparison.md)). Organisms sense, decide, move, eat, reproduce (exact copies), and die, with every unit of energy accounted for. Populations level off at a size set by the food supply.

A **tick** is one step of simulated time: every organism senses, acts and pays its energy costs once per tick.

## Running a simulation

```bash
uv run genesis run                                  # default config, results in data/runs/<run id>/
uv run genesis run --seed 7 --ticks 2000 --out data/runs/try-seed-7
uv run genesis run --help                           # every option
```

Each run directory holds `run.json` (seed, config, code version, status), `ticks.csv` (one row per tick) and `organisms.csv` (one row per organism that ever lived). The same config and seed always produce identical CSV files.

## Experiments and benchmarks

```bash
uv run python experiments/e001_controller_comparison.py   # E001: 20 runs, ~45 s
uv run python experiments/benchmark.py                    # speed at population 30-1000
```

Experiment definitions and results: [docs/experiments/](docs/experiments/). Recorded benchmarks: [docs/benchmarks.md](docs/benchmarks.md).

## Configuration

Runs are described by YAML files in `configs/`. [configs/default.yaml](configs/default.yaml) documents every field and its unit. Invalid files are rejected before anything runs:

```bash
uv run python -c "from genesis.core.config import load_config; print(load_config('configs/default.yaml'))"
```

## Requirements

- [uv](https://docs.astral.sh/uv/) 0.11 or newer. uv installs and manages Python for you, so you don't need a system Python 3.12.

## Setup

```bash
uv sync            # creates .venv with Python 3.12 and installs the locked dependencies
```

## Everyday commands

```bash
uv run pytest              # run the test suite
uv run ruff check .        # lint
uv run ruff format .       # auto-format
```

`uv run` executes a command inside the project's virtual environment, so you never need to activate it by hand.

## Layout

```text
src/genesis/   the importable package (simulation, evolution, analytics, ...)
tests/         automated tests (pytest)
configs/       YAML run configurations
experiments/   experiment and benchmark scripts
docs/          architecture, decisions, curriculum, experiment methodology
data/          generated run output (ignored by Git)
```

See [docs/architecture.md](docs/architecture.md) for how the pieces fit together.
