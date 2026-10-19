# Genesis Lab

A local-first artificial life laboratory. Digital organisms live in a 2D world: they sense food, move, eat, reproduce, mutate and evolve, and every experiment is recorded so it can be reproduced and analysed. Everything runs on your machine: no cloud services, no API keys.

Built as a learning project: the [curriculum](docs/curriculum.md) tracks the concepts covered so far.

**Status:** Milestones 1 (The Petri Dish), 2 (Genetics and Evolution) and 3 (The Science Lab) complete. Milestone 4 (Evolving Neural Brains) in progress.

## What it does

- **Ecosystem:** a bounded world with regrowing food. Organisms sense the nearest food, decide (random walk or food seeker), move, eat, pay energy costs, reproduce and die. Every unit of energy is accounted for and checked every tick.
- **Evolution:** each organism carries a genome (speed, sense range, turning, metabolic rate, reproduction threshold, and a neutral marker). Children inherit a mutated copy; trade-off costs make each gene's value matter.
- **Reproducibility:** the same config and seed always produce byte-identical results. Each run records its config, seed, code version and a fingerprint of the final state.
- **Science:** pre-registered experiments run in parallel from spec files, paired seeds, drift-only control runs, confidence intervals, effect sizes and significance tests (hand-written and cross-checked with SciPy).
- **Data:** every run validated into a Parquet data lake, queried with SQL (DuckDB), charted in experiment dashboards, and exportable with its own documentation and checksums.

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
uv run genesis run --config configs/neural.yaml --out data/runs/neural  # evolving neural brains (~10 s)
uv run genesis report data/runs/evo                           # writes data/runs/evo/report.html
open data/runs/evo/report.html
```

`uv run genesis run --help` lists every option.

To query runs together, convert them into the Parquet **data lake** (validated, ~10× smaller than the CSVs; see [docs/schema.md](docs/schema.md)):

```bash
uv run genesis lake ingest data/runs data/experiments    # writes data/lake/<table>/<run_id>.parquet
uv run genesis sql "SELECT condition, count(*) FROM completed_runs GROUP BY condition"
```

Worked SQL examples (joins, window functions, a recursive family tree): [docs/sql-examples.md](docs/sql-examples.md). Ten exercises about the real experiments, with hidden answers: [docs/sql-exercises.md](docs/sql-exercises.md).

A dashboard for a whole experiment (every run, plus medians and confidence intervals), built from the lake:

```bash
uv run genesis dashboard E003 --compare S_plenty:N_plenty --compare S_scarce:N_scarce
open data/dashboards/E003.html
```

Export an experiment (tables + column documentation + checksums) for analysis anywhere, then check it:

```bash
uv run genesis lake export --experiment E003 --out data/exports/E003    # Parquet; --format csv also works
uv run genesis lake verify data/exports/E003
uv run python experiments/independent_reanalysis.py data/exports/E003    # pandas + SciPy only
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
- [`neural.yaml`](configs/neural.yaml): `evolution.yaml` with each organism's own evolving neural brain as the controller and every expressed gene frozen, so only brains evolve ([how the brain works](docs/neural-networks.md)).

Invalid configs are rejected before anything runs, with an error naming the field.

## Experiments

Each experiment is defined (question, hypotheses, seeds, analysis) and committed **before** it runs; results are appended afterwards.

| | Question | Finding |
|---|---|---|
| [E001](docs/experiments/E001-controller-comparison.md) | Food seeker vs random walk | Seekers reach the population limit faster and leave less food; both settle at a similar size, set by the food supply |
| [E002](docs/experiments/E002-selection-machinery.md) | Does the evolution machinery work? | Yes: the positive control (cost-free metabolism) evolved down in 20/20 seeds; selection raised speed and reproduction threshold relative to drift |
| [E003](docs/experiments/E003-food-scarcity.md) | Does food scarcity change selection? | It raised selected sense range (adjusted p = 0.031; worth replicating); its control arm reproduced E002 |
| [E004](docs/experiments/E004-food-dose-response.md) | Is population proportional to food? | Yes: elasticity 0.992 [0.982, 1.001]; H1's formula within ~6% |
| [E005](docs/experiments/E005-mutation-diversity.md) | Does more mutation maintain more diversity? | Yes: ρ = 0.88, p ≈ 0.00005, meaningful; roughly √(rate) |
| [E006](docs/experiments/E006-founders-extinction.md) | Do fewer founders mean more extinction? | No monotonic effect (p = 0.42); an exploratory U-shape to test next |

```bash
uv run genesis experiment status experiments/specs/E002.yaml          # which runs exist / are stale
uv run genesis experiment run experiments/specs/E00N.yaml             # parallel, resumable, loads the lake
uv run python experiments/e002_selection_machinery.py --analyse-only  # re-analyse saved runs
uv run python experiments/benchmark.py [--sizes 30,1000,3000] [--evolution]  # speed, see docs/benchmarks.md
```

## Notebook

[notebooks/analysis-workflow.ipynb](notebooks/analysis-workflow.ipynb) walks through the whole workflow (define → run → SQL → pandas → intervals → tests → charts → export) on a small demo experiment. Open it in VS Code, pick the `.venv` kernel and *Run All* (~6 s). Clear its outputs before committing.

## Everyday commands

```bash
uv run pytest              # run the test suite (~2 min; minute-long stress tests are skipped)
uv run pytest -m slow      # the slow stress tests: 50,000 ticks, a 120-run batch
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
src/genesis/lake/          ETL into the Parquet lake, DuckDB views, exports
tests/                     automated tests (pytest)
configs/                   YAML run configurations
experiments/               experiment specs (specs/*.yaml), analysis and benchmark scripts
notebooks/                 the end-to-end analysis notebook
scripts/                   documentation builders (SQL exercises)
docs/                      architecture, decisions, curriculum, methodology, experiments, benchmarks
data/                      generated run output (ignored by Git)
```

## Documentation

- [Architecture](docs/architecture.md): how the pieces fit together, tick order, data formats
- [Decision log](docs/decision-log.md): each design decision, why, and the alternatives
- [Experiment design](docs/experiment-design.md): methodology and statistical rules
- [Curriculum](docs/curriculum.md): concepts covered, milestone by milestone
- [Database schema](docs/schema.md) and [data dictionary](docs/data-dictionary.md): tables, keys, every column
- [SQL examples](docs/sql-examples.md) and [SQL exercises](docs/sql-exercises.md)
- [Benchmarks](docs/benchmarks.md): recorded performance
- [Neural networks, by hand](docs/neural-networks.md): what an organism's brain computes, with a worked example
- [Roadmap](docs/roadmap/README.md): scope for Milestones 4–6 and how it maps onto this project
