# Genesis Lab: instructions for Claude Code sessions

## What this project is

An artificial life research platform built incrementally as a teaching project. The user is a technically curious beginner in Python, SQL and ML. Understanding matters as much as working code.

## Working rules

- **Milestone gating:** never start a new milestone without explicit user approval. **Milestones 1 and 2 complete. Milestone 3 (The Science Lab) approved 2026-10-19** with all recommended options; plan in docs/architecture.md ("Milestone 3 plan"). Stop before neural-network controllers (Milestone 4 needs approval). Stop after each numbered increment.
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
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run genesis run --seed 42 --out data/runs/<name>   # one recorded run
uv run genesis report data/runs/<name>               # HTML report (Plotly, offline)
uv run genesis lake ingest data/runs data/experiments  # validate + convert runs to data/lake/ (Parquet)
uv run genesis sql "SELECT ..."                      # query the lake (views: docs/schema.md)
uv run genesis dashboard E00N [--compare T:C]       # experiment dashboard from the lake
uv run genesis lake export --experiment E00N --out data/exports/E00N   # + README + manifest
```

## Simulation invariants (do not break)

- **Determinism:** same config + seed + environment → identical output. All randomness comes from `numpy.random.Generator` streams spawned from one `SeedSequence` per run, one stream per subsystem, in fixed order (setup, food, controller, reproduction, tiebreak, mutation); new streams are appended only at the end. Never use `random`, `np.random.<function>` global state, or iterate over sets/unordered collections in simulation code. Organisms are processed in ascending ID order.
- **Snapshot observation:** all organisms observe the same frozen world state before any action is applied.
- **Newborns** are inactive until the tick after their birth.
- **Food contention:** one meal per organism per tick; in-reach pairs resolved closest-first; exact ties are broken with the tiebreak stream (never by ID, which would bias toward older lineages). Organisms eat *before* paying costs.
- **Energy ledger:** initial + inflow − outflow == current total within `EnergyLedger.tolerance` (scaled to gross flow), checked by `Simulation.step()` every tick (`EnergyLedgerError`). Every new energy flow must be recorded in `EnergyLedger`, summed per tick with `math.fsum` (D-026).
- **Separation of concerns:** controllers are pure (observation → action) and never mutate the world; metrics are read-only.
- **Boundaries:** hard walls (positions clamped), not wrap-around.
- **Run records:** CSV output must stay byte-identical for identical config + seed + environment. A new TickSummary/organism field goes into the metrics column lists; never write nondeterministic values (timestamps, run IDs) into the CSVs.

## Code conventions

- src layout; package name `genesis`, distribution `genesis-lab`.
- Python 3.12, ruff (line length 100), type hints on public functions.
- Tests live in `tests/`, mirroring the module they cover.
- Generated data goes in `data/` (Git-ignored).
- UI work (Milestone 5) follows the user's global anti-vibe-code design rules.
