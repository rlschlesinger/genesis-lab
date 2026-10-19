# Genesis Lab

A local-first artificial life laboratory. Digital organisms live in a simulated 2D world, eat, reproduce and (from Milestone 2) evolve. Everything runs on your machine: no cloud services, no API keys.

**Status:** Milestone 1 (The Petri Dish), increment 1.7: a running, deterministic ecosystem. Organisms sense, decide, move, eat, reproduce (exact copies), and die, with every unit of energy accounted for. Populations level off at a size set by the food supply.

A **tick** is one step of simulated time: every organism senses, acts and pays its energy costs once per tick.

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
configs/       YAML run configurations (from increment 1.1)
docs/          architecture, decisions, curriculum, experiment methodology
data/          generated run output (ignored by Git)
```

See [docs/architecture.md](docs/architecture.md) for how the pieces fit together.
