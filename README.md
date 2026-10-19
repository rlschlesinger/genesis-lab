# Genesis Lab

A local-first artificial life laboratory. Digital organisms live in a 2D world: they sense food, move, eat, reproduce, mutate and evolve, and every experiment is recorded so it can be reproduced and analysed. Everything runs on your machine: no cloud services, no API keys.

Built as a learning project: the [curriculum](docs/curriculum.md) tracks the concepts covered so far.

**Status:** Milestones 1 (The Petri Dish) and 2 (Genetics and Evolution) complete. Milestone 3 (The Science Lab) not started.

## What it does

- **Ecosystem:** a bounded world with regrowing food. Organisms sense the nearest food, decide (random walk or food seeker), move, eat, pay energy costs, reproduce and die. Every unit of energy is accounted for and checked every tick.
- **Evolution:** each organism carries a genome (speed, sense range, turning, metabolic rate, reproduction threshold, and a neutral marker). Children inherit a mutated copy; trade-off costs make each gene's value matter.
- **Reproducibility:** the same config and seed always produce byte-identical results. Each run records its config, seed, code version and a fingerprint of the final state.
- **Science:** pre-registered experiments with paired seeds, drift-only control runs and hand-written significance tests.

A **tick** is one step of simulated time: every organism senses, acts and pays its energy costs once per tick.

## Setup

Requires [uv](https://docs.astral.sh/uv/) 0.11 or newer. uv installs and manages Python 3.12 for you.

```bash
uv sync            # creates .venv and installs the locked dependencies
```

## Quick start

```bash
uv run genesis run --seed 7 --out data/runs/first             # ecosystem, no evolution
uv run genesis run --config configs/evolution.yaml --out data/runs/evo   # with evolution (~6 s)
uv run genesis report data/runs/evo                           # writes data/runs/evo/report.html
open data/runs/evo/report.html
```

`uv run genesis run --help` lists every option.

To query runs together, convert them into the Parquet **data lake** (validated, ~10× smaller than the CSVs; see [docs/schema.md](docs/schema.md)):

```bash
uv run genesis lake ingest data/runs data/experiments    # writes data/lake/<table>/<run_id>.parquet
```

## What a run writes

| File | Contents |
|---|---|
| `run.json` | Seed, full config, git commit (and whether the code had uncommitted changes), versions, status, final-state fingerprint |
| `ticks.csv` | One row per tick (or every `recording.ticks_every` ticks, with births/deaths/meals summed in between): population, births, deaths, food, mean energy, founder lineages, mutations |
| `gene_stats.csv` | Per tick and gene: count, mean, standard deviation, min, max |
| `genomes.csv` | Every living genome, every 50 ticks and on the final tick |
| `organisms.csv` | One row per organism that ever lived: lineage, birth, death, lifetime totals, genes and traits |
| `mutations.csv` | Every gene change at every birth |
| `events.csv` | Optional log of births, deaths and meals (`recording.events`) |
| `report.html` | Charts, after `genesis report` (self-contained, works offline) |

## Configuration

Runs are described by YAML files in `configs/`:

- [`default.yaml`](configs/default.yaml): the Milestone 1 ecosystem, with mutation and trade-off costs off. Every field is documented with its unit.
- [`evolution.yaml`](configs/evolution.yaml): the same, plus mutation, trade-off costs (drag and sensing upkeep), a frozen turning gene and 20,000 ticks. A test keeps the two files from differing anywhere else.

Invalid configs are rejected before anything runs, with an error naming the field.

## Experiments

Each experiment is defined (question, hypotheses, seeds, analysis) and committed **before** it runs; results are appended afterwards.

| | Question | Finding |
|---|---|---|
| [E001](docs/experiments/E001-controller-comparison.md) | Food seeker vs random walk | Seekers reach the population limit faster and leave less food; both settle at a similar size, set by the food supply |
| [E002](docs/experiments/E002-selection-machinery.md) | Does the evolution machinery work? | Yes: the positive control (cost-free metabolism) evolved down in 20/20 seeds; selection raised speed and reproduction threshold relative to drift |
| [E003](docs/experiments/E003-food-scarcity.md) | Does food scarcity change selection? | It raised selected sense range (adjusted p = 0.031; worth replicating); its control arm reproduced E002 |

```bash
uv run python experiments/e002_selection_machinery.py                 # 60 runs, ~8 min
uv run python experiments/e002_selection_machinery.py --analyse-only  # re-analyse saved runs
uv run python experiments/benchmark.py                                # speed at population 30-1000
```

## Everyday commands

```bash
uv run pytest              # run the test suite
uv run ruff check .        # lint
uv run ruff format .       # auto-format
```

## Layout

```text
src/genesis/core/          world, food, organisms, movement, feeding, costs, energy ledger, simulation
src/genesis/intelligence/  sensing and controllers
src/genesis/evolution/     genome, mutation, reproduction
src/genesis/analytics/     run recording, provenance, experiments, significance tests
src/genesis/report/        HTML run reports
src/genesis/lake/          ETL into the Parquet data lake
tests/                     automated tests (pytest)
configs/                   YAML run configurations
experiments/               experiment and benchmark scripts
docs/                      architecture, decisions, curriculum, methodology, experiments, benchmarks
data/                      generated run output (ignored by Git)
```

## Documentation

- [Architecture](docs/architecture.md): how the pieces fit together, tick order, data formats
- [Decision log](docs/decision-log.md): each design decision, why, and the alternatives
- [Experiment design](docs/experiment-design.md): methodology and statistical rules
- [Curriculum](docs/curriculum.md): concepts covered, milestone by milestone
- [Database schema](docs/schema.md) and [data dictionary](docs/data-dictionary.md): tables, keys, every column
- [Benchmarks](docs/benchmarks.md): recorded performance
