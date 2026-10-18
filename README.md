# Genesis Lab

A local-first artificial life laboratory. Digital organisms live in a simulated 2D world, eat, reproduce and (from Milestone 2) evolve. Everything runs on your machine: no cloud services, no API keys.

**Status:** Milestone 1 (The Petri Dish), increment 1.0: project scaffold only.

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
