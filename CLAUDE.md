# Genesis Lab: instructions for Claude Code sessions

## What this project is

An artificial life research platform built incrementally as a teaching project. The user is a technically curious beginner in Python, SQL and ML. Understanding matters as much as working code.

## Working rules

- **Milestone gating:** never start a new milestone without explicit user approval. **Milestones 1–4 complete (2026-10-19). Milestone 5 (API and browser lab, roadmap chunks 05A–05B) has not been approved:** propose a plan and wait. Stop after each numbered increment. Scope for Milestones 4–6 is in `docs/roadmap/` (the user's chunk files, word for word); `docs/roadmap/README.md` says how each maps onto this project and which details are adapted (no Mesa, hard walls, `genesis` not `alife`).
- **Experiments:** define each one in `docs/experiments/E00N-*.md` (question, hypotheses, metrics, analysis) and `experiments/specs/E00N.yaml` (conditions, seeds), and commit both *before* running with `genesis experiment run`. Append results; never edit the definition afterwards. Label post-hoc findings as exploratory.
- **Notebooks:** commit them without outputs (tests/test_notebook.py checks); the test suite executes `notebooks/analysis-workflow.ipynb`.
- **Exercises for the user:** always say where to look, give the method, and put the answer at the bottom. Flag judgment calls.
- **Teaching loop for every substantial change:** problem → concept → proposed implementation → smallest useful increment → demonstrate → how to inspect/test → one small exercise → ask to proceed.
- **New dependencies:** explain why, name alternatives, add it in the increment that first needs it. Record significant ones in docs/decision-log.md.
- **Commits:** commit at the end of each increment and push to `origin` (github.com/rlschlesinger/genesis-lab, public). This repo's git email is the GitHub noreply address; never commit a personal email.
- **Never fabricate results.** Report what runs actually produced; separate observation from interpretation.
- After each milestone, update README.md, this file, and all of docs/.

## Commands

```bash
uv sync
uv run pytest                                        # fast suite (~2 min); slow stress tests are skipped
uv run pytest -m slow                                # the minute-long stress tests (tests/test_stress.py)
uv run ruff check . && uv run ruff format --check .
uv run python experiments/benchmark.py [--sizes 30,1000,3000] [--evolution]   # docs/benchmarks.md
uv run genesis run --seed 42 --out data/runs/<name>   # one recorded run
uv run genesis report data/runs/<name>               # HTML report (Plotly, offline)
uv run genesis inspect data/runs/<name> --tick T --organism ID [--weights]   # replay one decision
uv run genesis lake ingest data/runs data/experiments  # validate + convert runs to data/lake/ (Parquet)
uv run genesis sql "SELECT ..."                      # query the lake (views: docs/schema.md)
uv run genesis dashboard E00N [--compare T:C]       # experiment dashboard from the lake
uv run genesis lake export --experiment E00N --out data/exports/E00N   # + README + manifest
uv run python experiments/e007_neuroevolution.py --analyse-only --report   # E007 verdicts + results page
```

## Simulation invariants (do not break)

- **Determinism:** same config + seed + environment → identical output. All randomness comes from `numpy.random.Generator` streams spawned from one `SeedSequence` per run, one stream per subsystem, in fixed order (setup, food, controller, reproduction, tiebreak, mutation, brain); new streams are appended only at the end. Never use `random`, `np.random.<function>` global state, or iterate over sets/unordered collections in simulation code. Organisms are processed in ascending ID order.
- **Snapshot observation:** all organisms observe the same frozen world state before any action is applied.
- **Newborns** are inactive until the tick after their birth.
- **Food contention:** one meal per organism per tick; in-reach pairs resolved closest-first; exact ties are broken with the tiebreak stream (never by ID, which would bias toward older lineages). Organisms eat *before* paying costs.
- **Energy ledger:** initial + inflow − outflow == current total within `EnergyLedger.tolerance` (scaled to gross flow), checked by `Simulation.step()` every tick (`EnergyLedgerError`). Every new energy flow must be recorded in `EnergyLedger`, summed per tick with `math.fsum` (D-026).
- **Separation of concerns:** controllers are pure (observation → action) and never mutate the world; metrics are read-only.
- **Boundaries:** hard walls (positions clamped), not wrap-around.
- **Bit-identical optimizations only (D-036, D-038):** a speed-up may change *how* a value is computed only if every float comes out identical. The spatial grid (`core/spatial.py`) only proposes candidate pairs; the same `np.hypot` and `<=` decide. Array versions of scalar rules (`costs.living_costs`, `organism.spend_all`) must apply the same IEEE operations in the same order per element, and tests must assert equality with the scalar rule. Known traps: `math.hypot` ≠ `np.hypot`, `np.power` ≠ Python `**` (except exponents 0 and 1), reductions along a non-contiguous axis sum in a different order. Verify with `tests/test_regression.py` *and* a fresh digest comparison of long and large runs before merging.
- **Configs stay hashable across versions:** a new optional config section must be omitted from `model_dump` when absent (see `SimulationConfig._omit_absent_brain`), or every existing run's `config_hash` changes and completed experiments look stale.
- **Run records:** CSV output must stay byte-identical for identical config + seed + environment. A new TickSummary/organism field goes into the metrics column lists; never write nondeterministic values (timestamps, run IDs) into the CSVs.

## Code conventions

- src layout; package name `genesis`, distribution `genesis-lab`.
- Python 3.12, ruff (line length 100), type hints on public functions.
- Tests live in `tests/`, mirroring the module they cover.
- Generated data goes in `data/` (Git-ignored).
- UI work (Milestone 5) follows the user's global anti-vibe-code design rules.
